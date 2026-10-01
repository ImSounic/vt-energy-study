package nl.utwente.gsd.energy;

import java.io.IOException;
import java.util.Map;

/** Cumulative energy counters, read on demand. All values are microjoules. */
public interface EnergyReader {

    /** Reads every discovered counter. */
    Map<String, Long> readAll() throws IOException;

    /** Energy consumed between two readings of one counter, in microjoules. */
    long deltaFor(String domain, long start, long end);

    /** RAPL on Linux, IOReport on macOS. */
    static EnergyReader forThisMachine() throws IOException {
        String os = System.getProperty("os.name").toLowerCase();
        if (os.contains("mac")) return new IoReportReader();
        if (os.contains("linux")) return new RaplReader();
        throw new IOException("no energy reader for OS: " + os);
    }
}
