package nl.utwente.gsd.workload;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.ArrayList;
import java.util.List;

/**
 * Deterministic workloads for the concurrency energy study.
 *
 * <p>Compute-bound and blocking workloads are both provided because the
 * constructs under test have different design intents: virtual threads target
 * blocking (I/O-bound) work, while Fork-Join targets compute-bound
 * divide-and-conquer work. Measuring only one class would bias the comparison.
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
            double y0 = ((py + offset) % resolution) * 2.0 / resolution - 1.0;
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

    /** Builds {@code taskCount} near-identical (offset-shifted rows of the same grid) CPU-bound tasks of the given grid resolution. */
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
     * SLEEP task: blocks for a fixed duration.
     *
     * <p>{@link Thread#sleep} is a genuine blocking operation that causes a
     * virtual thread to unmount from its carrier, which is precisely the
     * mechanism under study, with a nominally controlled latency. It involves no
     * device; {@link #socket} adds real (loopback) network I/O.
     */
    public static List<Runnable> sleep(int taskCount, int blockMillis) {
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

    /** Request and reply size of the SOCKET workload, in bytes. */
    public static final int SOCKET_PAYLOAD = 64;

    /**
     * SOCKET task: one loopback TCP round trip to a {@link SocketDelayServer},
     * which replies {@code delay} ms after the request. One connection per task
     * keeps the I/O pattern identical across constructs.
     *
     * <p>The client closes with SO_LINGER 0 (an RST), so no port is left in
     * TIME_WAIT: at about 20 000 connections/s the ephemeral port range would
     * otherwise be exhausted within seconds. Any I/O failure is rethrown, so a
     * missing server fails the run instead of producing cheap, empty work.
     */
    public static List<Runnable> socket(int taskCount, int port) {
        InetSocketAddress server = new InetSocketAddress(InetAddress.getLoopbackAddress(), port);
        byte[] request = new byte[SOCKET_PAYLOAD];
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            tasks.add(() -> {
                try (Socket s = new Socket()) {
                    s.setSoLinger(true, 0);
                    s.setTcpNoDelay(true);
                    s.setSoTimeout(5_000);
                    s.connect(server, 5_000);
                    s.getOutputStream().write(request);
                    if (s.getInputStream().readNBytes(SOCKET_PAYLOAD).length != SOCKET_PAYLOAD) {
                        throw new IOException("short reply from " + server);
                    }
                } catch (IOException e) {
                    throw new UncheckedIOException(e);
                }
            });
        }
        return tasks;
    }

    /**
     * MIXED task: a request handler that computes, then waits on a remote call.
     * Every task first runs one Mandelbrot burst ({@link #mandelbrotEscapes} at
     * {@code resolution}), then blocks in {@link Thread#sleep} for
     * {@code blockMillis}. Unlike {@link #mixed}, which splits the tasks into
     * computing and blocking ones, both phases are inside every task.
     */
    public static List<Runnable> computeThenSleep(int taskCount, int resolution, int blockMillis) {
        List<Runnable> tasks = new ArrayList<>(taskCount);
        for (int i = 0; i < taskCount; i++) {
            final int offset = i;
            tasks.add(() -> {
                long r = mandelbrotEscapes(resolution, offset);
                if (r == Long.MIN_VALUE) throw new AssertionError("unreachable");
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
