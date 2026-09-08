package nl.utwente.gsd.workload;

import java.util.ArrayList;
import java.util.List;

/**
 * Deterministic workloads for the concurrency energy study.
 *
 * <p>Two classes are provided because the constructs under test have different
 * design intents: virtual threads target blocking (I/O-bound) work, while
 * Fork-Join targets compute-bound divide-and-conquer work. Measuring only one
 * class would bias the comparison.
 */
public final class Workloads {

    private Workloads() {}

    /**
     * CPU-bound task: counts Mandelbrot escape iterations over a fixed grid.
     * Chosen because it is deterministic, allocation-free, and was part of the
     * benchmark set used by Pinto, Castor &amp; Liu (OOPSLA 2014).
     */
    public static long mandelbrotEscapes(int resolution, int offset) {
        final int maxIter = 500;
        long escapes = 0;
        for (int py = 0; py < resolution; py++) {
            double y0 = (py + offset) * 2.0 / resolution - 1.0;
            for (int px = 0; px < resolution; px++) {
                double x0 = px * 3.0 / resolution - 2.0;
                double x = 0.0, y = 0.0;
                int iter = 0;
                while (x * x + y * y <= 4.0 && iter < maxIter) {
                    double xt = x * x - y * y + x0;
                    y = 2.0 * x * y + y0;
                    x = xt;
                    iter++;
                }
                escapes += iter;
            }
        }
        return escapes;
    }

    /** Builds {@code taskCount} identical CPU-bound tasks of the given grid resolution. */
    public static List<Runnable> cpuBound(int taskCount, int resolution) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            final int offset = i;
            tasks.add(() -> {
                long result = mandelbrotEscapes(resolution, offset);
                if (result == Long.MIN_VALUE) throw new AssertionError("unreachable");
            });
        }
        return tasks;
    }

    /**
     * I/O-bound task: blocks for a fixed duration.
     *
     * <p>{@link Thread#sleep} is a genuine blocking operation that causes a
     * virtual thread to unmount from its carrier, which is precisely the
     * mechanism under study, and it makes latency an exactly controlled
     * independent variable. A real-socket variant is planned for Assignment 2
     * to address the external-validity threat this introduces.
     */
    public static List<Runnable> ioBound(int taskCount, int blockMillis) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            tasks.add(() -> {
                try {
                    Thread.sleep(blockMillis);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
        }
        return tasks;
    }

    /** Mixed workload: a fraction of tasks block, the remainder compute. */
    public static List<Runnable> mixed(int taskCount, int resolution, int blockMillis, double blockingFraction) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            final int offset = i;
            final boolean blocking = (i / (double) taskCount) < blockingFraction;
            tasks.add(() -> {
                if (blocking) {
                    try { Thread.sleep(blockMillis); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                } else {
                    long r = mandelbrotEscapes(resolution, offset);
                    if (r == Long.MIN_VALUE) throw new AssertionError("unreachable");
                }
            });
        }
        return tasks;
    }
}
