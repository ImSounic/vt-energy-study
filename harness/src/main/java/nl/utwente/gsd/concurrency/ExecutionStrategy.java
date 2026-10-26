package nl.utwente.gsd.concurrency;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

/**
 * The five Java thread management constructs under comparison, plus two
 * persistent-pool controls.
 *
 * <p>SEQUENTIAL is the reference of Pinto, Castor &amp; Liu (OOPSLA 2014); the
 * next three replicate their constructs; VIRTUAL_THREADS is the JEP 444
 * construct that did not exist in 2014. FIXED_POOL and FORK_JOIN build and shut
 * down their pool inside every operation, while VIRTUAL_THREADS reuses the
 * JVM-wide carrier pool; FIXED_POOL_PERSISTENT and FORK_JOIN_PERSISTENT are the
 * control that reuses one pool per trial (see {@link #open(int)}).
 *
 * <p>All arms fail loudly and identically if any task throws: silent partial
 * work would corrupt the energy measurements.
 */
public enum ExecutionStrategy {

    /** All tasks run one after another in the caller thread; {@code parallelism} is ignored. */
    SEQUENTIAL {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) {
            for (Runnable task : tasks) task.run();
        }
    },

    /** One platform thread created per task, as in the 2014 "explicit thread creation" arm. */
    PLATFORM_THREADS {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            List<Throwable> failures = Collections.synchronizedList(new ArrayList<>());
            List<Thread> threads = new ArrayList<>(tasks.size());
            for (Runnable task : tasks) {
                Thread t = new Thread(task);
                t.setUncaughtExceptionHandler((thread, e) -> failures.add(e));
                threads.add(t);
                t.start();
            }
            for (Thread t : threads) t.join();
            if (!failures.isEmpty()) {
                throw new IllegalStateException("task failed", failures.get(0));
            }
        }
    },

    /** Fixed-size platform thread pool (ExecutorService). */
    FIXED_POOL {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (ExecutorService pool = Executors.newFixedThreadPool(parallelism)) {
                List<Future<Void>> futures = pool.invokeAll(toCallables(tasks));
                awaitAll(futures);
            }
        }
    },

    /**
     * Work-stealing Fork/Join used as designed: a {@link RecursiveAction} halves
     * the task list down to single tasks. Try-with-resources so teardown (close =
     * shutdown + await termination) is inside the measured window, mirroring
     * FIXED_POOL. The pool is bounded at {@code parallelism} threads, see
     * {@link #boundedForkJoinPool(int)}.
     */
    FORK_JOIN {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) {
            if (tasks.isEmpty()) return;
            try (ForkJoinPool pool = boundedForkJoinPool(parallelism)) {
                pool.invoke(new Split(tasks, 0, tasks.size()));
            }
        }
    },

    /**
     * Control for FIXED_POOL: the same fixed-size pool, created once per
     * {@link Session} (one JMH trial) and reused by every operation, as a
     * server would. Pool construction and teardown fall outside the measured
     * window.
     */
    FIXED_POOL_PERSISTENT {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (Session session = open(parallelism)) {
                session.execute(tasks);
            }
        }

        @Override
        public Session open(int parallelism) {
            ExecutorService pool = Executors.newFixedThreadPool(parallelism);
            return new Session() {
                @Override
                public void execute(List<Runnable> tasks) throws InterruptedException {
                    awaitAll(pool.invokeAll(toCallables(tasks)));
                }

                @Override
                public void close() {
                    pool.close();
                }
            };
        }
    },

    /**
     * Control for FORK_JOIN: the same bounded Fork/Join pool and recursive
     * halving, with the pool created once per {@link Session} (one JMH trial)
     * and reused by every operation.
     */
    FORK_JOIN_PERSISTENT {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (Session session = open(parallelism)) {
                session.execute(tasks);
            }
        }

        @Override
        public Session open(int parallelism) {
            ForkJoinPool pool = boundedForkJoinPool(parallelism);
            return new Session() {
                @Override
                public void execute(List<Runnable> tasks) {
                    if (tasks.isEmpty()) return;
                    pool.invoke(new Split(tasks, 0, tasks.size()));
                }

                @Override
                public void close() {
                    pool.close();
                }
            };
        }
    },

    /**
     * JEP 444 virtual threads: one virtual thread per task, multiplexed over a
     * carrier ForkJoinPool. The {@code parallelism} argument is deliberately
     * ignored — carrier count is set by the JVM and controlled in experiments
     * via the system property {@code jdk.virtualThreadScheduler.parallelism}.
     */
    VIRTUAL_THREADS {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (ExecutorService pool = Executors.newVirtualThreadPerTaskExecutor()) {
                List<Future<Void>> futures = pool.invokeAll(toCallables(tasks));
                awaitAll(futures);
            }
        }
    };

    public abstract void execute(List<Runnable> tasks, int parallelism) throws InterruptedException;

    /**
     * Opens a session that runs operations at {@code parallelism} until closed.
     * For the persistent controls the session owns one pool that every operation
     * reuses; for all other constructs it calls {@link #execute(List, int)}, so
     * their per-operation behaviour is unchanged.
     */
    public Session open(int parallelism) {
        return new Session() {
            @Override
            public void execute(List<Runnable> tasks) throws InterruptedException {
                ExecutionStrategy.this.execute(tasks, parallelism);
            }

            @Override
            public void close() {
            }
        };
    }

    /** A sequence of operations of one construct at one concurrency level. */
    public interface Session extends AutoCloseable {
        void execute(List<Runnable> tasks) throws InterruptedException;

        /** Shuts down and awaits any pool the session owns. */
        @Override
        void close();
    }

    /**
     * A Fork/Join pool that never exceeds {@code parallelism} threads. By default
     * a worker that joins a stolen, still-running (e.g. sleeping) subtask may
     * start a compensation thread, so the effective concurrency would exceed the
     * concurrency level; maximumPoolSize = parallelism with saturate = true makes
     * the joining worker wait instead (A3 plan, A3-D2).
     */
    static ForkJoinPool boundedForkJoinPool(int parallelism) {
        return new ForkJoinPool(parallelism, ForkJoinPool.defaultForkJoinWorkerThreadFactory, null,
                false, parallelism, parallelism, 1, pool -> true, 60, TimeUnit.SECONDS);
    }

    /** Recursive halving of [lo, hi) down to single tasks. */
    static final class Split extends RecursiveAction {
        private final List<Runnable> tasks;
        private final int lo;
        private final int hi;

        Split(List<Runnable> tasks, int lo, int hi) {
            this.tasks = tasks;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected void compute() {
            if (hi - lo == 1) {
                tasks.get(lo).run();
                return;
            }
            int mid = (lo + hi) >>> 1;
            invokeAll(new Split(tasks, lo, mid), new Split(tasks, mid, hi));
        }
    }

    /** Waits for every future; a failed task is rethrown with its real cause (resultNow() drops it). */
    static void awaitAll(List<Future<Void>> futures) throws InterruptedException {
        for (Future<Void> f : futures) {
            try {
                f.get();
            } catch (ExecutionException e) {
                throw new IllegalStateException("task failed", e.getCause());
            }
        }
    }

    static List<Callable<Void>> toCallables(List<Runnable> tasks) {
        List<Callable<Void>> callables = new ArrayList<>(tasks.size());
        for (Runnable task : tasks) {
            callables.add(() -> { task.run(); return null; });
        }
        return callables;
    }
}
