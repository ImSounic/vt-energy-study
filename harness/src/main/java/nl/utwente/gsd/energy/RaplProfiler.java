package nl.utwente.gsd.energy;

import org.openjdk.jmh.profile.ProfilerException;
import org.openjdk.jmh.results.AggregationPolicy;
import org.openjdk.jmh.results.Result;
import org.openjdk.jmh.results.ScalarResult;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Intel RAPL energy per iteration (Linux powercap sysfs), plus a snapshot of
 * the mean core frequency per core class at the end of each iteration
 * ({@code freq.P_MHz}, {@code freq.E_MHz}, {@code freq.LPE_MHz}) so that the
 * power regime of every measured iteration is explicit.
 * Register with: -prof nl.utwente.gsd.energy.RaplProfiler
 */
public class RaplProfiler extends EnergyProfiler {

    private final CpuFreq freq;

    public RaplProfiler() throws ProfilerException {
        super(open(), "rapl");
        try {
            freq = CpuFreq.forThisMachine();
        } catch (IOException e) {
            throw new ProfilerException("Cannot read cpufreq: " + e.getMessage());
        }
    }

    @Override
    protected List<Result> extraResults() {
        List<Result> out = new ArrayList<>();
        for (Map.Entry<String, Double> e : freq.meanMHzByClass().entrySet()) {
            out.add(new ScalarResult("freq." + e.getKey() + "_MHz", e.getValue(), "MHz", AggregationPolicy.AVG));
        }
        return out;
    }

    private static RaplReader open() throws ProfilerException {
        try {
            return new RaplReader();
        } catch (IOException e) {
            throw new ProfilerException(
                "Cannot initialise RAPL: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Intel RAPL energy per iteration (powercap sysfs)";
    }
}
