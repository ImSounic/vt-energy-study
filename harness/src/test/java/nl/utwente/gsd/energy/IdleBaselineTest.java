package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;

import java.util.Locale;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class IdleBaselineTest {

    private static final EnergyReader FAKE = new EnergyReader() {
        @Override public Map<String, Long> readAll() { return Map.of(); }
        @Override public long deltaFor(String domain, long start, long end) { return end - start; }
    };

    @Test
    void wattsAreJoulesOverSeconds() {
        Map<String, Double> w = IdleBaseline.watts(FAKE,
                Map.of("CPU_Energy", 0L), Map.of("CPU_Energy", 30_000_000L), 60.0);
        assertEquals(0.5, w.get("CPU_Energy"), 1e-9);
    }

    @Test
    void jsonUsesDotDecimalsRegardlessOfLocale() {
        Locale previous = Locale.getDefault();
        Locale.setDefault(Locale.forLanguageTag("nl-NL"));
        try {
            String json = IdleBaseline.toJson(60.0, Map.of("CPU_Energy", 0.5));
            assertTrue(json.contains("\"seconds\": 60.000"), json);
            assertTrue(json.contains("\"CPU_Energy\": 0.500000"), json);
        } finally {
            Locale.setDefault(previous);
        }
    }
}
