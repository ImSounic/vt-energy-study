package nl.utwente.gsd;

import nl.utwente.gsd.concurrency.ExecutionStrategy;
import nl.utwente.gsd.workload.Workloads;
import org.openjdk.jmh.annotations.*;
import org.openjdk.jmh.infra.Blackhole;

import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Sweeps execution strategy x parallelism x workload type for the energy study.
 *
 * <p>Pool construction, thread creation, and the resulting allocation/GC
 * pressure are deliberately included in the measured window: they are part of
 * each construct's real cost. Note: the parallelism parameter is a no-op for
 * PLATFORM_THREADS and VIRTUAL_THREADS (see plan §Task 1.8); run scripts must
 * exclude those cells or dedupe them in analysis.
 */
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.MILLISECONDS)
@State(Scope.Benchmark)
@Fork(value = 5, jvmArgs = {"-Xms2g", "-Xmx2g", "-XX:+UseG1GC"})
@Warmup(iterations = 10, time = 1)
@Measurement(iterations = 20, time = 1)
public class ConcurrencyEnergyBenchmark {

    @Param({"PLATFORM_THREADS", "FIXED_POOL", "FORK_JOIN", "VIRTUAL_THREADS"})
    public ExecutionStrategy strategy;

    /** Concurrency level; sweeps the "Lambda curve" from the 2014 baseline. */
    @Param({"1", "2", "4", "8", "16", "32", "64", "128"})
    public int parallelism;

    @Param({"CPU", "IO"})
    public String workloadType;

    private List<Runnable> tasks;

    @Setup(Level.Trial)
    public void setUp() {
        // Task count is held constant so total work is identical across all
        // levels of `parallelism`; only the degree of concurrency varies.
        tasks = switch (workloadType) {
            case "CPU" -> Workloads.cpuBound(256, 128);
            case "IO"  -> Workloads.ioBound(256, 10);
            default -> throw new IllegalArgumentException("unknown workload: " + workloadType);
        };
    }

    @Benchmark
    public void execute(Blackhole bh) throws InterruptedException {
        strategy.execute(tasks, parallelism);
        bh.consume(tasks.size());
    }
}
