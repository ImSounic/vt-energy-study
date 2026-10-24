package nl.utwente.gsd.tools;

import nl.utwente.gsd.workload.Workloads;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * AX5: calibrates the per-task wait d of the blocking workloads. Measures the
 * latency of {@code Thread.sleep(10)} on a platform thread and on a virtual
 * thread, one sleep at a time, and optionally the SOCKET round trip to a
 * running {@link nl.utwente.gsd.workload.SocketDelayServer}.
 *
 * <p>Usage: java -cp benchmarks.jar nl.utwente.gsd.tools.LatencyCalibration
 * &lt;out.json&gt; [sleeps=10000] [socketPort rtts=1000]
 */
public final class LatencyCalibration {

    private LatencyCalibration() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 4) {
            System.err.println("usage: LatencyCalibration <out.json> [sleeps] [socketPort [rtts]]");
            System.exit(2);
        }
        int sleeps = args.length > 1 ? Integer.parseInt(args[1]) : 10_000;
        Map<String, Map<String, Double>> out = new LinkedHashMap<>();
        out.put("sleep_platform", summarize(sleeps(sleeps, 10, false)));
        out.put("sleep_virtual", summarize(sleeps(sleeps, 10, true)));
        if (args.length > 2) {
            int rtts = args.length > 3 ? Integer.parseInt(args[3]) : 1_000;
            out.put("socket_rtt", summarize(roundTrips(rtts, Integer.parseInt(args[2]))));
        }
        String json = toJson(out);
        Files.writeString(Path.of(args[0]), json);
        System.out.print(json);
    }

    /** Latency in ms of {@code n} consecutive {@code Thread.sleep(millis)} calls. */
    static double[] sleeps(int n, int millis, boolean virtual) throws InterruptedException {
        double[] ms = new double[n];
        Runnable body = () -> {
            try {
                for (int i = 0; i < n; i++) {
                    long t0 = System.nanoTime();
                    Thread.sleep(millis);
                    ms[i] = (System.nanoTime() - t0) / 1e6;
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };
        Thread t = virtual ? Thread.ofVirtual().start(body) : Thread.ofPlatform().start(body);
        t.join();
        return ms;
    }

    /** Latency in ms of {@code n} consecutive SOCKET-workload round trips. */
    static double[] roundTrips(int n, int port) {
        Runnable task = Workloads.socket(1, port).get(0);
        double[] ms = new double[n];
        for (int i = 0; i < n; i++) {
            long t0 = System.nanoTime();
            task.run();
            ms[i] = (System.nanoTime() - t0) / 1e6;
        }
        return ms;
    }

    static Map<String, Double> summarize(double[] values) {
        double[] v = values.clone();
        Arrays.sort(v);
        Map<String, Double> s = new LinkedHashMap<>();
        s.put("n", (double) v.length);
        s.put("mean", Arrays.stream(v).average().orElse(Double.NaN));
        s.put("min", v[0]);
        s.put("median", quantile(v, 0.5));
        s.put("p90", quantile(v, 0.9));
        s.put("p99", quantile(v, 0.99));
        s.put("max", v[v.length - 1]);
        return s;
    }

    /** Linear interpolation between order statistics of a sorted array. */
    private static double quantile(double[] sorted, double q) {
        double pos = q * (sorted.length - 1);
        int lo = (int) Math.floor(pos);
        int hi = Math.min(lo + 1, sorted.length - 1);
        return sorted[lo] + (pos - lo) * (sorted[hi] - sorted[lo]);
    }

    private static String toJson(Map<String, Map<String, Double>> out) {
        return out.entrySet().stream()
                .map(e -> "\"" + e.getKey() + "\": {" + e.getValue().entrySet().stream()
                        .map(s -> String.format(Locale.ROOT, "\"%s\": %.4f", s.getKey(), s.getValue()))
                        .collect(Collectors.joining(", ")) + "}")
                .collect(Collectors.joining(", ", "{", "}\n"));
    }
}
