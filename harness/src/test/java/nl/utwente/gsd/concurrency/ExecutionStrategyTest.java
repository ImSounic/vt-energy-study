package nl.utwente.gsd.concurrency;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;

import java.util.List;
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
    void allFourConstructsArePresent() {
        assertEquals(4, ExecutionStrategy.values().length);
    }
}
