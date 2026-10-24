package nl.utwente.gsd.energy;

import org.openjdk.jmh.infra.BenchmarkParams;
import org.openjdk.jmh.infra.IterationParams;
import org.openjdk.jmh.profile.InternalProfiler;
import org.openjdk.jmh.results.AggregationPolicy;
import org.openjdk.jmh.results.IterationResult;
import org.openjdk.jmh.results.Result;
import org.openjdk.jmh.results.ScalarResult;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

/**
 * JMH profiler that attributes energy to each iteration by reading cumulative
 * counters once before and once after it. Counters are never polled during the
 * measured region: high-frequency polling suppresses C-states and inflates
 * idle power (Raffin &amp; Trystram, IEEE TPDS 2025).
 */
public abstract class EnergyProfiler implements InternalProfiler {

    private final EnergyReader reader;
    private final String prefix;
    private Map<String, Long> start;
    private long startNanos;

    protected EnergyProfiler(EnergyReader reader, String prefix) {
        this.reader = reader;
        this.prefix = prefix;
    }

    @Override
    public void beforeIteration(BenchmarkParams bp, IterationParams ip) {
        try {
            start = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("energy read failed at iteration start", e);
        }
        startNanos = System.nanoTime();
    }

    @Override
    public Collection<? extends Result> afterIteration(
            BenchmarkParams bp, IterationParams ip, IterationResult result) {
        long endNanos = System.nanoTime();
        double windowSeconds = (endNanos - startNanos) / 1e9;
        Map<String, Long> end;
        try {
            end = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("energy read failed at iteration end", e);
        }
        reader.checkFresh(start, end, windowSeconds);
        List<Result> out = results(prefix, reader, start, end,
                result.getMetadata().getAllOps(), windowSeconds);
        out.addAll(extraResults());
        return out;
    }

    /**
     * Further per-iteration values read at the iteration-end boundary (after
     * the energy counters, so they cannot perturb the energy window).
     * Default: none.
     */
    protected List<Result> extraResults() {
        return List.of();
    }

    /** Per-domain J and J/op, plus the length of the energy window in seconds. */
    static List<Result> results(String prefix, EnergyReader reader, Map<String, Long> start,
                                Map<String, Long> end, long ops, double windowSeconds) {
        List<Result> out = new ArrayList<>();
        out.add(new ScalarResult(prefix + ".window_s", windowSeconds, "s", AggregationPolicy.AVG));
        for (Map.Entry<String, Long> e : start.entrySet()) {
            String domain = e.getKey();
            double joules = reader.deltaFor(domain, e.getValue(), end.get(domain)) / 1_000_000.0;
            out.add(new ScalarResult(prefix + "." + domain + ".J", joules, "J", AggregationPolicy.AVG));
            if (ops > 0) {
                out.add(new ScalarResult(prefix + "." + domain + ".J_per_op",
                        joules / ops, "J/op", AggregationPolicy.AVG));
            }
        }
        return out;
    }
}
