package nl.utwente.gsd.concurrency;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

/**
 * The five Java thread management constructs under comparison.
 *
 * <p>SEQUENTIAL is the reference of Pinto, Castor &amp; Liu (OOPSLA 2014); the
 * next three replicate their constructs; VIRTUAL_THREADS is the JEP 444
 * construct that did not exist in 2014.
 *
 * <p>All five arms fail loudly and identically if any task throws: silent
 * partial work would corrupt the energy measurements.
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
                for (Future<Void> f : futures) f.resultNow();
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
                for (Future<Void> f : futures) f.resultNow();
            }
        }
    };

    public abstract void execute(List<Runnable> tasks, int parallelism) throws InterruptedException;

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

    static List<Callable<Void>> toCallables(List<Runnable> tasks) {
        List<Callable<Void>> callables = new ArrayList<>(tasks.size());
        for (Runnable task : tasks) {
            callables.add(() -> { task.run(); return null; });
        }
        return callables;
    }
}
