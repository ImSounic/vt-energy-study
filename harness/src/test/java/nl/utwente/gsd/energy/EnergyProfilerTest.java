package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import org.openjdk.jmh.results.Result;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class EnergyProfilerTest {

    /** Fake reader: deltas are plain differences. */
    private static final EnergyReader FAKE = new EnergyReader() {
        @Override public Map<String, Long> readAll() { return Map.of(); }
        @Override public long deltaFor(String domain, long start, long end) { return end - start; }
    };

    private static double score(List<Result> results, String label) {
        return results.stream().filter(r -> r.getLabel().equals(label)).findFirst()
                .orElseThrow(() -> new AssertionError("missing " + label)).getScore();
    }

    @Test
    void reportsJoulesJoulesPerOpAndWindow() {
        Map<String, Long> start = new LinkedHashMap<>(Map.of("CPU_Energy", 1_000_000L));
        Map<String, Long> end = Map.of("CPU_Energy", 9_000_000L);
        List<Result> r = EnergyProfiler.results("ioreport", FAKE, start, end, 4, 5.0);
        assertEquals(8.0, score(r, "ioreport.CPU_Energy.J"), 1e-9);
        assertEquals(2.0, score(r, "ioreport.CPU_Energy.J_per_op"), 1e-9);
        assertEquals(5.0, score(r, "ioreport.window_s"), 1e-9);
    }

    @Test
    void omitsPerOpMetricWhenNoOpsCompleted() {
        List<Result> r = EnergyProfiler.results("rapl", FAKE,
                Map.of("pkg", 0L), Map.of("pkg", 5_000_000L), 0, 1.0);
        assertTrue(r.stream().noneMatch(x -> x.getLabel().endsWith("J_per_op")));
    }
}
