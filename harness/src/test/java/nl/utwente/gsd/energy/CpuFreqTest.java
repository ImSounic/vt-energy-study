package nl.utwente.gsd.energy;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CpuFreqTest {

    private static void cpu(Path root, int id, String capacity, String avgKHz, String curKHz) throws IOException {
        Path cpu = root.resolve("cpu" + id);
        Files.createDirectories(cpu.resolve("cpufreq"));
        if (capacity != null) Files.writeString(cpu.resolve("cpu_capacity"), capacity + "\n");
        if (avgKHz != null) Files.writeString(cpu.resolve("cpufreq/cpuinfo_avg_freq"), avgKHz + "\n");
        if (curKHz != null) Files.writeString(cpu.resolve("cpufreq/scaling_cur_freq"), curKHz + "\n");
    }

    @Test
    void meanFrequencyPerCoreClass(@TempDir Path root) throws IOException {
        cpu(root, 0, "1024", "4000000", "1");
        cpu(root, 1, "1024", "2000000", "1");
        cpu(root, 2, "774", null, "3000000");     // no avg_freq: falls back to scaling_cur_freq
        cpu(root, 3, "312", "garbage", null);     // unreadable: skipped
        Files.createDirectories(root.resolve("cpufreq"));  // non-cpu entries are ignored

        Map<String, Double> mhz = CpuFreq.fromSysfs(root).meanMHzByClass();

        assertEquals(Map.of("P", 3000.0, "E", 3000.0), mhz);
    }

    @Test
    void homogeneousMachineHasOnlyPClass(@TempDir Path root) throws IOException {
        cpu(root, 0, null, "1000000", null);
        cpu(root, 1, null, "3000000", null);

        assertEquals(Map.of("P", 2000.0), CpuFreq.fromSysfs(root).meanMHzByClass());
    }

    @Test
    void classNamesFollowTopologyScript(@TempDir Path root) throws IOException {
        cpu(root, 0, "1024", "1000000", null);
        cpu(root, 1, "774", "1000000", null);
        cpu(root, 2, "312", "1000000", null);
        cpu(root, 10, "312", "3000000", null);

        assertEquals(Map.of("P", 1000.0, "E", 1000.0, "LPE", 2000.0),
                CpuFreq.fromSysfs(root).meanMHzByClass());
    }
}
