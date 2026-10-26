package nl.utwente.gsd.concurrency;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
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

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void taskFailureKeepsItsCause(ExecutionStrategy strategy) {
        RuntimeException boom = new RuntimeException("boom");
        Throwable thrown = assertThrows(Throwable.class, () -> strategy.execute(List.of(() -> { throw boom; }), 2));
        Throwable root = thrown;
        while (root != boom && root.getCause() != null) root = root.getCause();
        assertSame(boom, root, strategy + " lost the task's exception: " + thrown);
    }

    @Test
    void allFiveConstructsAndBothControlsArePresent() {
        assertEquals(List.of(ExecutionStrategy.SEQUENTIAL, ExecutionStrategy.PLATFORM_THREADS,
                        ExecutionStrategy.FIXED_POOL, ExecutionStrategy.FORK_JOIN,
                        ExecutionStrategy.FIXED_POOL_PERSISTENT, ExecutionStrategy.FORK_JOIN_PERSISTENT,
                        ExecutionStrategy.VIRTUAL_THREADS),
                List.of(ExecutionStrategy.values()));
    }

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void sessionRunsEveryTaskOfEveryOperationExactlyOnce(ExecutionStrategy strategy) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        List<Runnable> tasks = IntStream.range(0, 256)
                .<Runnable>mapToObj(i -> counter::incrementAndGet)
                .toList();

        try (ExecutionStrategy.Session session = strategy.open(4)) {
            for (int op = 0; op < 5; op++) session.execute(tasks);
        }

        assertEquals(5 * 256, counter.get(), strategy + " did not run every task exactly once");
    }

    @ParameterizedTest
    @EnumSource(ExecutionStrategy.class)
    void sessionPropagatesTaskFailureWithItsCause(ExecutionStrategy strategy) {
        RuntimeException boom = new RuntimeException("boom");
        try (ExecutionStrategy.Session session = strategy.open(2)) {
            Throwable thrown = assertThrows(Throwable.class, () -> session.execute(List.of(() -> { throw boom; })));
            Throwable root = thrown;
            while (root != boom && root.getCause() != null) root = root.getCause();
            assertSame(boom, root, strategy + " lost the task's exception: " + thrown);
        }
    }

    /**
     * The persistent controls reuse one pool: once the first operation has
     * started the pool's p threads, later operations start no new ones.
     */
    @ParameterizedTest
    @EnumSource(value = ExecutionStrategy.class, names = {"FIXED_POOL_PERSISTENT", "FORK_JOIN_PERSISTENT"})
    void persistentPoolsStartNoThreadsAfterTheFirstOperation(ExecutionStrategy strategy) throws Exception {
        List<Set<Thread>> perOperation = threadsPerOperation(strategy, 2, 4);

        assertEquals(2, perOperation.get(0).size(), strategy + " first operation: " + perOperation.get(0));
        for (Set<Thread> later : perOperation.subList(1, perOperation.size())) {
            assertTrue(perOperation.get(0).containsAll(later), strategy + " started new threads: " + later);
        }
    }

    /** The contrast that makes the reuse test meaningful: the per-operation pools start fresh threads. */
    @ParameterizedTest
    @EnumSource(value = ExecutionStrategy.class, names = {"FIXED_POOL", "FORK_JOIN"})
    void perOperationPoolsStartNewThreadsEveryOperation(ExecutionStrategy strategy) throws Exception {
        List<Set<Thread>> perOperation = threadsPerOperation(strategy, 2, 4);

        for (Set<Thread> later : perOperation.subList(1, perOperation.size())) {
            assertTrue(Collections.disjoint(perOperation.get(0), later), strategy + " reused a thread");
        }
    }

    @ParameterizedTest
    @EnumSource(value = ExecutionStrategy.class, names = {"FIXED_POOL_PERSISTENT", "FORK_JOIN_PERSISTENT"})
    void closingAPersistentSessionStopsItsThreads(ExecutionStrategy strategy) throws Exception {
        Set<Thread> seen = Collections.synchronizedSet(new HashSet<>());
        try (ExecutionStrategy.Session session = strategy.open(2)) {
            session.execute(sleepingTasks(4, 20, () -> seen.add(Thread.currentThread())));
        }
        for (Thread t : seen) {
            t.join(5_000);
            assertFalse(t.isAlive(), strategy + " left " + t + " running after close");
        }
    }

    /** The threads that ran each of {@code operations} operations of 8 sleeping tasks in one session. */
    private static List<Set<Thread>> threadsPerOperation(ExecutionStrategy strategy, int parallelism,
                                                         int operations) throws Exception {
        List<Set<Thread>> perOperation = new ArrayList<>();
        try (ExecutionStrategy.Session session = strategy.open(parallelism)) {
            for (int op = 0; op < operations; op++) {
                Set<Thread> seen = Collections.synchronizedSet(new HashSet<>());
                session.execute(sleepingTasks(8, 20, () -> seen.add(Thread.currentThread())));
                perOperation.add(seen);
            }
        }
        return perOperation;
    }

    private static List<Runnable> sleepingTasks(int count, long millis, Runnable before) {
        return IntStream.range(0, count)
                .<Runnable>mapToObj(i -> () -> {
                    before.run();
                    try {
                        Thread.sleep(millis);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                })
                .toList();
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

    @Test
    void persistentForkJoinRunsTasksAsForkJoinTasksAtTheRequestedParallelism() throws Exception {
        List<Integer> parallelism = Collections.synchronizedList(new ArrayList<>());
        List<Runnable> tasks = IntStream.range(0, 16)
                .<Runnable>mapToObj(i -> () -> {
                    assertTrue(ForkJoinTask.inForkJoinPool());
                    parallelism.add(ForkJoinTask.getPool().getParallelism());
                })
                .toList();

        try (ExecutionStrategy.Session session = ExecutionStrategy.FORK_JOIN_PERSISTENT.open(3)) {
            session.execute(tasks);
            session.execute(tasks);
        }

        assertEquals(32, parallelism.size());
        assertTrue(parallelism.stream().allMatch(p -> p == 3));
    }

    /**
     * The concurrency level is a hard bound for the pools: on a blocking
     * workload no pool may run more than p tasks at once (for Fork/Join
     * this requires compensation threads to be disabled, A3-D2).
     */
    @ParameterizedTest
    @EnumSource(value = ExecutionStrategy.class,
            names = {"FIXED_POOL", "FORK_JOIN", "FIXED_POOL_PERSISTENT", "FORK_JOIN_PERSISTENT"})
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

        try (ExecutionStrategy.Session session = strategy.open(2)) {
            for (int op = 0; op < 2; op++) {  // the second operation runs on a reused persistent pool
                long start = System.nanoTime();
                session.execute(tasks);
                long elapsedMillis = (System.nanoTime() - start) / 1_000_000;

                assertTrue(highWater.get() <= 2, strategy + " ran " + highWater.get() + " tasks at once");
                assertTrue(elapsedMillis >= 190, strategy + " finished in " + elapsedMillis + " ms");
            }
        }
    }
}
