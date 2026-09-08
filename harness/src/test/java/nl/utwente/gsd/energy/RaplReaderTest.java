package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class RaplReaderTest {

    @Test
    void deltaHandlesNormalIncrease() {
        assertEquals(500L, RaplReader.delta(1000L, 1500L, 262143328850L));
    }

    @Test
    void deltaHandlesWraparound() {
        long max = 262143328850L;
        assertEquals(300L, RaplReader.delta(max - 100L, 200L, max));
    }

    @Test
    void deltaIsZeroWhenUnchanged() {
        assertEquals(0L, RaplReader.delta(42L, 42L, 262143328850L));
    }

    @Test
    void discoversAtLeastOneDomainOnThisMachine() throws Exception {
        RaplReader reader = new RaplReader();
        Map<String, Long> readings = reader.readAll();
        assertFalse(readings.isEmpty(), "expected at least one RAPL domain");
        readings.values().forEach(v -> assertTrue(v >= 0));
    }

    @Test
    void consecutiveReadsAreMonotonicOrWrapped() throws Exception {
        RaplReader reader = new RaplReader();
        Map<String, Long> first = reader.readAll();
        long sink = 0;
        for (int i = 0; i < 50_000_000; i++) sink += i;
        assertTrue(sink != Long.MIN_VALUE);
        Map<String, Long> second = reader.readAll();
        for (String domain : first.keySet()) {
            long d = reader.deltaFor(domain, first.get(domain), second.get(domain));
            assertTrue(d > 0, "expected positive energy delta for " + domain);
        }
    }
}
