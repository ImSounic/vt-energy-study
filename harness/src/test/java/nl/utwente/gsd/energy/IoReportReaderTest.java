package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledOnOs;
import org.junit.jupiter.api.condition.OS;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

class IoReportReaderTest {

    @Test
    void deltaIsDifferenceOfCumulativeValues() {
        assertEquals(1_100_000L, IoReportReader.delta(17_262_809_000L, 17_263_909_000L));
    }

    @Test
    void deltaRejectsCounterGoingBackwards() {
        assertThrows(IllegalStateException.class, () -> IoReportReader.delta(10L, 5L));
    }

    @Test
    @EnabledOnOs(OS.MAC)
    void discoversCpuClusterChannels() throws Exception {
        Map<String, Long> readings = new IoReportReader().readAll();
        assertTrue(readings.containsKey("CPU_Energy"), "channels: " + readings.keySet());
        assertTrue(readings.containsKey("ECPU"));
        assertTrue(readings.containsKey("PCPU"));
        readings.values().forEach(v -> assertTrue(v >= 0));
        long cpu = readings.get("CPU_Energy");
        long clusters = readings.get("ECPU") + readings.get("PCPU");
        assertTrue(Math.abs(cpu - clusters) <= cpu / 1000,
                "CPU_Energy should equal ECPU + PCPU (unit scaling): " + cpu + " vs " + clusters);
    }

    @Test
    @EnabledOnOs(OS.MAC)
    void cpuEnergyAdvancesWhilePowermetricsRefreshes() throws Exception {
        assumeTrue(powermetricsRunning(),
                "needs 'sudo powermetrics' running; counters are frozen otherwise");
        IoReportReader reader = new IoReportReader();
        long before = reader.readAll().get("CPU_Energy");
        long sink = 0;
        long until = System.nanoTime() + 1_500_000_000L;
        while (System.nanoTime() < until) sink += sink * 31 + 7;
        assertTrue(sink != 42);
        long after = reader.readAll().get("CPU_Energy");
        long delta = reader.deltaFor("CPU_Energy", before, after);
        assertTrue(delta > 50_000 && delta < 30_000_000,
                "1.5 s single-thread burn should be 0.05-30 J, got " + delta + " uJ");
    }

    @Test
    void checkFreshRejectsFrozenCanaryOverLongWindow() {
        assertThrows(IllegalStateException.class, () -> IoReportReader.checkFresh(5L, 5L, 1.0));
    }

    @Test
    void checkFreshAcceptsAdvancingOrShortWindows() {
        assertDoesNotThrow(() -> IoReportReader.checkFresh(5L, 6L, 1.0));
        assertDoesNotThrow(() -> IoReportReader.checkFresh(5L, 5L, 0.2));
    }

    private static boolean powermetricsRunning() throws Exception {
        return new ProcessBuilder("pgrep", "-x", "powermetrics").start().waitFor() == 0;
    }
}
