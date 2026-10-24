package nl.utwente.gsd.energy;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Stream;

/**
 * Snapshot of the current core frequency per core class (Linux cpufreq sysfs),
 * read only when asked: the profiler calls it at iteration boundaries, never
 * during the measured region.
 *
 * <p>Classes follow scripts/topology.sh: distinct {@code cpu_capacity} values in
 * descending order are P, E and LPE. Each CPU is read from
 * {@code cpuinfo_avg_freq} (APERF/MPERF based) or, if that is absent or
 * unreadable, {@code scaling_cur_freq}; CPUs with neither are skipped.
 */
public final class CpuFreq {

    private static final String[] CLASS_NAMES = {"P", "E", "LPE"};

    /** Core class name to the cpufreq directories of its CPUs. */
    private final Map<String, List<Path>> classes;

    private CpuFreq(Map<String, List<Path>> classes) {
        this.classes = classes;
    }

    public static CpuFreq forThisMachine() throws IOException {
        return fromSysfs(Path.of("/sys/devices/system/cpu"));
    }

    static CpuFreq fromSysfs(Path cpuRoot) throws IOException {
        TreeMap<Integer, List<Path>> byCapacity = new TreeMap<>(java.util.Comparator.reverseOrder());
        try (Stream<Path> entries = Files.list(cpuRoot)) {
            for (Path cpu : entries.filter(p -> p.getFileName().toString().matches("cpu\\d+")).sorted().toList()) {
                Path freq = cpu.resolve("cpufreq");
                if (!Files.isDirectory(freq)) continue;
                byCapacity.computeIfAbsent(capacity(cpu), c -> new ArrayList<>()).add(freq);
            }
        }
        Map<String, List<Path>> classes = new LinkedHashMap<>();
        int i = 0;
        for (List<Path> cpus : byCapacity.values()) {
            if (i == CLASS_NAMES.length) break;
            classes.put(CLASS_NAMES[i++], cpus);
        }
        return new CpuFreq(classes);
    }

    private static int capacity(Path cpu) {
        try {
            return Integer.parseInt(Files.readString(cpu.resolve("cpu_capacity")).trim());
        } catch (IOException | NumberFormatException e) {
            return 0; // homogeneous machines expose no capacity: one class
        }
    }

    /** Mean current frequency in MHz per class; classes without a readable CPU are omitted. */
    public Map<String, Double> meanMHzByClass() {
        Map<String, Double> out = new LinkedHashMap<>();
        for (Map.Entry<String, List<Path>> e : classes.entrySet()) {
            double sum = 0;
            int n = 0;
            for (Path freq : e.getValue()) {
                Long kHz = readKHz(freq.resolve("cpuinfo_avg_freq"));
                if (kHz == null) kHz = readKHz(freq.resolve("scaling_cur_freq"));
                if (kHz == null) continue;
                sum += kHz;
                n++;
            }
            if (n > 0) out.put(e.getKey(), sum / n / 1000.0);
        }
        return out;
    }

    private static Long readKHz(Path file) {
        try {
            return Long.parseLong(Files.readString(file).trim());
        } catch (IOException | NumberFormatException e) {
            return null; // absent, or EAGAIN on an idle CPU
        }
    }
}
