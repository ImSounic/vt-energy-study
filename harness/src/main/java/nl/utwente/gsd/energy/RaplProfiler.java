package nl.utwente.gsd.energy;

import org.openjdk.jmh.infra.BenchmarkParams;
import org.openjdk.jmh.infra.IterationParams;
import org.openjdk.jmh.profile.InternalProfiler;
import org.openjdk.jmh.profile.ProfilerException;
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
 * JMH profiler that attributes RAPL energy to each measurement iteration.
 * Register with: -prof nl.utwente.gsd.energy.RaplProfiler
 */
public class RaplProfiler implements InternalProfiler {

    private final RaplReader reader;
    private Map<String, Long> start;

    public RaplProfiler() throws ProfilerException {
        try {
            this.reader = new RaplReader();
        } catch (IOException e) {
            throw new ProfilerException(
                "Cannot initialise RAPL: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Intel RAPL energy per iteration (powercap sysfs)";
    }

    @Override
    public void beforeIteration(BenchmarkParams bp, IterationParams ip) {
        try {
            start = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("RAPL read failed at iteration start", e);
        }
    }

    @Override
    public Collection<? extends Result> afterIteration(
            BenchmarkParams bp, IterationParams ip, IterationResult result) {

        Map<String, Long> end;
        try {
            end = reader.readAll();
        } catch (IOException e) {
            throw new IllegalStateException("RAPL read failed at iteration end", e);
        }

        long ops = result.getMetadata().getMeasuredOps();
        List<Result> out = new ArrayList<>();

        for (Map.Entry<String, Long> e : start.entrySet()) {
            String domain = e.getKey();
            long endValue = end.get(domain);

            double joules = reader.deltaFor(domain, e.getValue(), endValue) / 1_000_000.0;
            out.add(new ScalarResult("rapl." + domain + ".J",
                    joules, "J", AggregationPolicy.AVG));
            if (ops > 0) {
                out.add(new ScalarResult("rapl." + domain + ".J_per_op",
                        joules / ops, "J/op", AggregationPolicy.AVG));
            }
        }
        return out;
    }
}
