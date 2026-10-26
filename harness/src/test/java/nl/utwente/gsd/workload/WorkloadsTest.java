package nl.utwente.gsd.workload;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class WorkloadsTest {

    @Test
    void cpuBoundProducesRequestedTaskCount() {
        List<Runnable> tasks = Workloads.cpuBound(50, 1000);
        assertEquals(50, tasks.size());
    }

    @Test
    void cpuBoundTasksAreDeterministic() {
        assertEquals(Workloads.mandelbrotEscapes(64, 0),
                     Workloads.mandelbrotEscapes(64, 0));
    }

    @Test
    void cpuBoundTasksActuallyComputeSomething() {
        assertTrue(Workloads.mandelbrotEscapes(64, 0) > 0);
    }

    @Test
    void sleepProducesRequestedTaskCount() {
        List<Runnable> tasks = Workloads.sleep(30, 1);
        assertEquals(30, tasks.size());
    }

    @Test
    void sleepTasksBlockForApproximatelyTheRequestedTime() {
        List<Runnable> tasks = Workloads.sleep(1, 50);
        long startNanos = System.nanoTime();
        tasks.get(0).run();
        long elapsedMillis = (System.nanoTime() - startNanos) / 1_000_000;
        assertTrue(elapsedMillis >= 45, "expected >=45ms block, got " + elapsedMillis);
    }

    @Test
    void computeThenSleepProducesRequestedTaskCount() {
        assertEquals(256, Workloads.computeThenSleep(256, 64, 10).size());
    }

    @Test
    void computeThenSleepTaskComputesAndThenBlocks() {
        Runnable task = Workloads.computeThenSleep(1, 64, 10).get(0);
        long startNanos = System.nanoTime();
        task.run();
        long elapsedMillis = (System.nanoTime() - startNanos) / 1_000_000;
        assertTrue(elapsedMillis >= 10, "expected >=10ms (burst + 10ms sleep), got " + elapsedMillis);
    }
}
