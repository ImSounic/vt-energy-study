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
public final class RaplReader implements EnergyReader {

    private final Map<String, Path> domains = new LinkedHashMap<>();
    private final Map<String, Long> maxRange = new LinkedHashMap<>();

    public RaplReader() throws IOException {
        Path base = Path.of("/sys/class/powercap");
        try (Stream<Path> entries = Files.list(base)) {
            try {
                entries.filter(p -> p.getFileName().toString().startsWith("intel-rapl:"))
                       .filter(p -> Files.isReadable(p.resolve("energy_uj")))
                       .sorted()
                       .forEach(this::register);
            } catch (UncheckedIOException e) {
                // register() can race a permission change between the isReadable
                // filter and the actual read (TOCTOU); surface it as the checked
                // IOException that callers such as RaplProfiler already handle.
                throw e.getCause();
            }
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

    /**
     * Test-only constructor: seeds max ranges without touching sysfs, so the
     * plausibility check in {@link #deltaFor} can be unit-tested on machines
     * where RAPL access has not been granted. Package-private by design.
     */
    RaplReader(Map<String, Long> maxRanges) {
        this.maxRange.putAll(maxRanges);
    }

    /**
     * Energy delta in microjoules for a named domain, correcting for wraparound.
     *
     * @throws IllegalStateException if the computed delta exceeds maxRange/2,
     *         which under the single-wrap assumption documented on
     *         {@link #delta(long, long, long)} indicates a multi-wrap or
     *         clock-skew condition rather than a plausible measurement.
     */
    public long deltaFor(String domain, long start, long end) {
        Long max = maxRange.get(domain);
        if (max == null) throw new IllegalArgumentException("unknown domain: " + domain);
        long d = delta(start, end, max);
        if (d > max / 2) {
            throw new IllegalStateException(
                "implausible energy delta — possible multi-wrap or clock skew");
        }
        return d;
    }

    /**
     * Energy delta in microjoules, correcting for counter wraparound.
     * Reading only start and end without this correction is the defect
     * van Kempen et al. (ASE 2025) identified in earlier RAPL tooling.
     *
     * <p>Note that {@code max_energy_range_uj} is the maximum representable
     * counter value, not the modulus, so each wrap event undercounts by one
     * energy unit (~61 µJ on this machine) — quantitatively irrelevant at
     * per-iteration deltas of 10–100 J, and consistent with how PAPI and
     * pyRAPL handle the same correction.
     *
     * <p>This correction assumes at most one wrap between the two reads. All
     * four domains on the target machine have {@code max_energy_range_uj}
     * ≈ 262 kJ; at 300 W sustained a single wrap takes ≈ 874 s, so the ~1 s
     * iteration windows used here sit about three orders of magnitude below
     * double-wrap territory. {@link #deltaFor} enforces this bound by
     * rejecting deltas above maxRange/2.
     */
    public static long delta(long start, long end, long maxRange) {
        return end >= start ? end - start : end + maxRange - start;
    }

    public Map<String, Long> maxRanges() {
        return Map.copyOf(maxRange);
    }
}
