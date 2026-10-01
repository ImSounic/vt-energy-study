package nl.utwente.gsd.energy;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Measures idle power per energy domain over a fixed window, for idle-baseline
 * subtraction. Usage:
 * java -cp benchmarks.jar nl.utwente.gsd.energy.IdleBaseline &lt;seconds&gt; &lt;out.json&gt;
 */
public final class IdleBaseline {

    private IdleBaseline() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: IdleBaseline <seconds> <out.json>");
            System.exit(2);
        }
        double seconds = Double.parseDouble(args[0]);
        EnergyReader reader = EnergyReader.forThisMachine();
        Map<String, Long> start = reader.readAll();
        long t0 = System.nanoTime();
        Thread.sleep((long) (seconds * 1000));
        long t1 = System.nanoTime();
        Map<String, Long> end = reader.readAll();
        double window = (t1 - t0) / 1e9;
        String json = toJson(window, watts(reader, start, end, window));
        Files.writeString(Path.of(args[1]), json);
        System.out.print(json);
    }

    static Map<String, Double> watts(EnergyReader reader, Map<String, Long> start,
                                     Map<String, Long> end, double seconds) {
        Map<String, Double> out = new LinkedHashMap<>();
        for (Map.Entry<String, Long> e : start.entrySet()) {
            long uj = reader.deltaFor(e.getKey(), e.getValue(), end.get(e.getKey()));
            out.put(e.getKey(), uj / 1e6 / seconds);
        }
        return out;
    }

    static String toJson(double seconds, Map<String, Double> watts) {
        String body = watts.entrySet().stream()
                .map(e -> String.format(Locale.ROOT, "\"%s\": %.6f", e.getKey(), e.getValue()))
                .collect(Collectors.joining(", "));
        return String.format(Locale.ROOT, "{\"seconds\": %.3f, \"watts\": {%s}}%n", seconds, body);
    }
}
