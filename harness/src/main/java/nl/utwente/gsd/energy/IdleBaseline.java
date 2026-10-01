package nl.utwente.gsd.energy;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
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
        Thread.sleep(2000); // let JVM start-up (JIT, class loading) settle before the idle window
        Map<String, Long> start = reader.readAll();
        long t0 = System.nanoTime();
        Thread.sleep((long) (seconds * 1000));
        long t1 = System.nanoTime();
        Map<String, Long> end = reader.readAll();
        double window = (t1 - t0) / 1e9;
        reader.checkFresh(start, end, window);
        Map<String, Double> watts = watts(reader, start, end, window);
        List<String> frozen = frozen(watts);
        if (!frozen.isEmpty()) {
            System.err.println("warning: no energy recorded for " + frozen + " (counter not refreshed?)");
        }
        String json = toJson(window, watts, frozen);
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

    /** Domains whose measured power is exactly zero, in map order. */
    static List<String> frozen(Map<String, Double> watts) {
        List<String> out = new ArrayList<>();
        for (Map.Entry<String, Double> e : watts.entrySet()) {
            if (e.getValue() == 0.0) out.add(e.getKey());
        }
        return out;
    }

    static String toJson(double seconds, Map<String, Double> watts, List<String> frozen) {
        String body = watts.entrySet().stream()
                .map(e -> String.format(Locale.ROOT, "\"%s\": %.6f", e.getKey(), e.getValue()))
                .collect(Collectors.joining(", "));
        String frozenBody = frozen.stream()
                .map(d -> "\"" + d + "\"")
                .collect(Collectors.joining(", "));
        return String.format(Locale.ROOT, "{\"seconds\": %.3f, \"watts\": {%s}, \"frozen\": [%s]}%n",
                seconds, body, frozenBody);
    }
}
