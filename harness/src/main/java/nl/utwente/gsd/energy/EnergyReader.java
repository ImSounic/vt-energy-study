package nl.utwente.gsd.energy;

import java.io.IOException;
import java.util.Map;

/** Cumulative energy counters, read on demand. All values are microjoules. */
public interface EnergyReader {

    /** Reads every discovered counter. */
    Map<String, Long> readAll() throws IOException;

    /** Energy consumed between two readings of one counter, in microjoules. */
    long deltaFor(String domain, long start, long end);

    /**
     * Fails if the counters evidently did not advance over a window of the given
     * length. Default: no check (RAPL counters always advance).
     */
    default void checkFresh(Map<String, Long> start, Map<String, Long> end, double seconds) {}

    /** RAPL on Linux, IOReport on macOS. */
    static EnergyReader forThisMachine() throws IOException {
        String os = System.getProperty("os.name").toLowerCase(java.util.Locale.ROOT);
        if (os.contains("mac")) return new IoReportReader();
        if (os.contains("linux")) return new RaplReader();
        throw new IOException("no energy reader for OS: " + os);
    }
}
