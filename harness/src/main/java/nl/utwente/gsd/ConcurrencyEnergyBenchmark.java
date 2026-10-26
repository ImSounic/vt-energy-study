package nl.utwente.gsd;

import nl.utwente.gsd.concurrency.ExecutionStrategy;
import nl.utwente.gsd.workload.Workloads;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Sweeps construct x concurrency level x workload for the energy study.
 *
 * <p>Pool construction, thread creation, and the resulting allocation/GC
 * pressure are deliberately included in the measured window: they are part of
 * each construct's real cost. The controls FIXED_POOL_PERSISTENT and
 * FORK_JOIN_PERSISTENT instead build their pool once per trial (in
 * {@link #setUp()}) and reuse it, to measure how much of that cost is pool
 * construction; they are run only through {@code -p strategy=...}.
 *
 * <p>{@code parallelism} is the pool size (FIXED_POOL), the parallelism
 * (FORK_JOIN), or the carrier count (VIRTUAL_THREADS). The carrier count cannot
 * be set in-process: run with
 * {@code -jvmArgsAppend "-Djdk.virtualThreadScheduler.parallelism=p
 * -Djdk.virtualThreadScheduler.maxPoolSize=p"} (never {@code -jvmArgs}, which
 * would drop the flags below); setup fails if it does not match. SEQUENTIAL and
 * PLATFORM_THREADS have no concurrency level; run them once, with p = 1.
 *
 * <p>MIXED models a request handler that computes and then waits on a remote
 * call: each task runs a Mandelbrot burst at resolution {@value #MIXED_RESOLUTION},
 * then sleeps 10 ms like SLEEP. The CPU workload's resolution 128 takes about
 * 5.7 ms per task on the M4; the cost scales with the grid points (measured
 * 128/64 ratio 3.8-3.9x), so resolution 64 is a burst of about 1.5 ms.
 *
 * <p>SOCKET needs a running {@link nl.utwente.gsd.workload.SocketDelayServer}
 * whose port is passed as {@code -Dvtenergy.socket.port}.
 */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@State(Scope.Benchmark)
@Fork(value = 10, jvmArgs = {"-Xms2g", "-Xmx2g", "-XX:+UseG1GC", "--enable-native-access=ALL-UNNAMED"})
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 5, time = 5)
public class ConcurrencyEnergyBenchmark {

    static final String CARRIER_PROPERTY = "jdk.virtualThreadScheduler.parallelism";
    static final String SOCKET_PORT_PROPERTY = "vtenergy.socket.port";

    /** Tasks per operation, identical at every concurrency level. */
    static final int TASKS = 256;

    /** Mandelbrot resolution of the MIXED workload's CPU burst (about 1.5 ms on an M4 P core). */
    static final int MIXED_RESOLUTION = 64;

    @Param({"SEQUENTIAL", "PLATFORM_THREADS", "FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"})
    public ExecutionStrategy strategy;

    /** Concurrency level; sweeps the "Lambda curve" from the 2014 baseline. */
    @Param({"1", "2", "4", "8", "16", "64", "256"})
    public int parallelism;

    @Param({"CPU", "SLEEP", "SOCKET", "MIXED"})
    public String workloadType;

    private List<Runnable> tasks;
    private ExecutionStrategy.Session session;

    @Setup(Level.Trial)
    public void setUp() {
        checkCarrierCount(strategy, parallelism, System.getProperty(CARRIER_PROPERTY));
        if (strategy == ExecutionStrategy.VIRTUAL_THREADS) {
            System.out.println("VT carriers = " + System.getProperty(CARRIER_PROPERTY));
        }
        tasks = switch (workloadType) {
            case "CPU" -> Workloads.cpuBound(TASKS, 128);
            case "SLEEP" -> Workloads.sleep(TASKS, 10);
            case "SOCKET" -> Workloads.socket(TASKS, socketPort(Integer.getInteger(SOCKET_PORT_PROPERTY)));
            case "MIXED" -> Workloads.computeThenSleep(TASKS, MIXED_RESOLUTION, 10);
            default -> throw new IllegalArgumentException("unknown workload: " + workloadType);
        };
        session = strategy.open(parallelism);
    }

    @TearDown(Level.Trial)
    public void tearDown() {
        if (session != null) session.close();
    }

    @Benchmark
    public void execute(Blackhole bh) throws InterruptedException {
        session.execute(tasks);
        bh.consume(tasks.size());
    }

    /** Fails unless a VT run's carrier count equals its concurrency level. */
    static void checkCarrierCount(ExecutionStrategy strategy, int parallelism, String carrierProperty) {
        if (strategy != ExecutionStrategy.VIRTUAL_THREADS) return;
        if (!String.valueOf(parallelism).equals(carrierProperty)) {
            throw new IllegalStateException("VIRTUAL_THREADS at parallelism " + parallelism
                    + " needs -D" + CARRIER_PROPERTY + "=" + parallelism + ", got " + carrierProperty);
        }
    }

    static int socketPort(Integer port) {
        if (port == null) {
            throw new IllegalStateException("SOCKET needs -D" + SOCKET_PORT_PROPERTY
                    + "=<port> of a running SocketDelayServer");
        }
        return port;
    }
}
