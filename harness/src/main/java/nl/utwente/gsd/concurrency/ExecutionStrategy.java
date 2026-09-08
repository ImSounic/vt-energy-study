package nl.utwente.gsd.concurrency;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ForkJoinPool;

/**
 * The four Java thread management constructs under comparison.
 *
 * <p>The first three replicate Pinto, Castor &amp; Liu (OOPSLA 2014);
 * VIRTUAL_THREADS is the JEP 444 construct that did not exist in 2014.
 */
public enum ExecutionStrategy {

    /** One platform thread created per task, as in the 2014 "explicit thread creation" arm. */
    PLATFORM_THREADS {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            List<Thread> threads = new ArrayList<>(tasks.size());
            for (Runnable task : tasks) {
                Thread t = new Thread(task);
                threads.add(t);
                t.start();
            }
            for (Thread t : threads) t.join();
        }
    },

    /** Fixed-size platform thread pool (ExecutorService). */
    FIXED_POOL {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            try (ExecutorService pool = Executors.newFixedThreadPool(parallelism)) {
                pool.invokeAll(toCallables(tasks));
            }
        }
    },

    /** Work-stealing Fork-Join pool. */
    FORK_JOIN {
        @Override
        public void execute(List<Runnable> tasks, int parallelism) throws InterruptedException {
            ForkJoinPool pool = new ForkJoinPool(parallelism);
            try {
                pool.invokeAll(toCallables(tasks));
            } finally {
                pool.shutdown();
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
                pool.invokeAll(toCallables(tasks));
            }
        }
    };

    public abstract void execute(List<Runnable> tasks, int parallelism) throws InterruptedException;

    static List<Callable<Void>> toCallables(List<Runnable> tasks) {
        List<Callable<Void>> callables = new ArrayList<>(tasks.size());
        for (Runnable task : tasks) {
            callables.add(() -> { task.run(); return null; });
        }
        return callables;
    }
}
