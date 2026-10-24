package nl.utwente.gsd.concurrency;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.IntStream;

import static org.junit.jupiter.api.Assertions.*;

class ExecutionStrategyTest {

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void runsEveryTaskExactlyOnce(ExecutionStrategy strategy) throws Exception {
        int taskCount = 1000;
        AtomicInteger counter = new AtomicInteger();
        List<Runnable> tasks = IntStream.range(0, taskCount)
                .<Runnable>mapToObj(i -> counter::incrementAndGet)
                .toList();

        strategy.execute(tasks, 4);

        assertEquals(taskCount, counter.get(),
                strategy + " did not run every task exactly once");
    }

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void propagatesNoExceptionForEmptyTaskList(ExecutionStrategy strategy) throws Exception {
        assertDoesNotThrow(() -> strategy.execute(List.of(), 4));
    }

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void propagatesTaskFailure(ExecutionStrategy strategy) {
        List<Runnable> tasks = List.of(() -> { throw new RuntimeException("boom"); });
        assertThrows(Throwable.class, () -> strategy.execute(tasks, 4),
                strategy + " swallowed a task failure");
    }

    @Test
    void allFiveConstructsArePresent() {
        assertEquals(List.of(ExecutionStrategy.SEQUENTIAL, ExecutionStrategy.PLATFORM_THREADS,
                        ExecutionStrategy.FIXED_POOL, ExecutionStrategy.FORK_JOIN,
                        ExecutionStrategy.VIRTUAL_THREADS),
                List.of(ExecutionStrategy.values()));
    }

    @Test
    void sequentialRunsInCallerThread() throws Exception {
        Thread caller = Thread.currentThread();
        List<Thread> seen = Collections.synchronizedList(new ArrayList<>());
        List<Runnable> tasks = IntStream.range(0, 10)
                .<Runnable>mapToObj(i -> () -> seen.add(Thread.currentThread()))
                .toList();

        ExecutionStrategy.SEQUENTIAL.execute(tasks, 4);

        assertEquals(10, seen.size());
        assertTrue(seen.stream().allMatch(t -> t == caller));
    }

    @Test
    void forkJoinRunsTasksAsForkJoinTasksAtTheRequestedParallelism() throws Exception {
        List<Integer> parallelism = Collections.synchronizedList(new ArrayList<>());
        List<Runnable> tasks = IntStream.range(0, 16)
                .<Runnable>mapToObj(i -> () -> {
                    assertTrue(ForkJoinTask.inForkJoinPool());
                    parallelism.add(ForkJoinTask.getPool().getParallelism());
                })
                .toList();

        ExecutionStrategy.FORK_JOIN.execute(tasks, 3);

        assertEquals(16, parallelism.size());
        assertTrue(parallelism.stream().allMatch(p -> p == 3));
    }

    /**
     * The concurrency level is a hard bound for the pools: on a blocking
     * workload neither pool may run more than p tasks at once (for Fork/Join
     * this requires compensation threads to be disabled, A3-D2).
     */
    @ParameterizedTest
    @EnumSource(value = ExecutionStrategy.class, names = {"FIXED_POOL", "FORK_JOIN"})
    void boundedPoolsRespectConcurrencyLevel(ExecutionStrategy strategy) throws Exception {
        AtomicInteger running = new AtomicInteger();
        AtomicInteger highWater = new AtomicInteger();
        List<Runnable> tasks = IntStream.range(0, 8)
                .<Runnable>mapToObj(i -> () -> {
                    highWater.accumulateAndGet(running.incrementAndGet(), Math::max);
                    try {
                        Thread.sleep(50);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                    running.decrementAndGet();
                })
                .toList();

        long start = System.nanoTime();
        strategy.execute(tasks, 2);
        long elapsedMillis = (System.nanoTime() - start) / 1_000_000;

        assertTrue(highWater.get() <= 2, strategy + " ran " + highWater.get() + " tasks at once");
        assertTrue(elapsedMillis >= 190, strategy + " finished in " + elapsedMillis + " ms");
    }
}
