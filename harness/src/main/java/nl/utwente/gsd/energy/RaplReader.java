package nl.utwente.gsd.energy;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Stream;

/**
 * Reads Intel RAPL energy counters via the Linux powercap sysfs interface.
 *
 * <p>Counters are read on demand only — never polled — because high-frequency
 * RAPL polling suppresses deep C-state residency and inflates idle power
 * (Raffin &amp; Trystram, IEEE TPDS 36(1):96-107, 2025).
 */
public final class RaplReader {

    private final Map<String, Path> domains = new LinkedHashMap<>();
    private final Map<String, Long> maxRange = new LinkedHashMap<>();

    public RaplReader() throws IOException {
        Path base = Path.of("/sys/class/powercap");
        try (Stream<Path> entries = Files.list(base)) {
            entries.filter(p -> p.getFileName().toString().startsWith("intel-rapl:"))
                   .filter(p -> Files.isReadable(p.resolve("energy_uj")))
                   .sorted()
                   .forEach(this::register);
        }
        if (domains.isEmpty()) {
            throw new IOException(
                "No readable RAPL domains found. Run scripts/enable-rapl.sh first.");
        }
    }

    private void register(Path dir) {
        try {
            String name = Files.readString(dir.resolve("name")).trim();
            String key = dir.getFileName().toString() + ":" + name;
            long max = Long.parseLong(
                Files.readString(dir.resolve("max_energy_range_uj")).trim());
            domains.put(key, dir.resolve("energy_uj"));
            maxRange.put(key, max);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }

    /** Reads every discovered domain. Values are microjoules. */
    public Map<String, Long> readAll() throws IOException {
        Map<String, Long> out = new LinkedHashMap<>();
        for (Map.Entry<String, Path> e : domains.entrySet()) {
            out.put(e.getKey(), Long.parseLong(Files.readString(e.getValue()).trim()));
        }
        return out;
    }

    /** Energy delta in microjoules for a named domain, correcting for wraparound. */
    public long deltaFor(String domain, long start, long end) {
        Long max = maxRange.get(domain);
        if (max == null) throw new IllegalArgumentException("unknown domain: " + domain);
        return delta(start, end, max);
    }

    /**
     * Energy delta in microjoules, correcting for counter wraparound.
     * Reading only start and end without this correction is the defect
     * van Kempen et al. (ASE 2025) identified in earlier RAPL tooling.
     */
    public static long delta(long start, long end, long maxRange) {
        return end >= start ? end - start : end + maxRange - start;
    }

    public Map<String, Long> maxRanges() {
        return Map.copyOf(maxRange);
    }
}
