package nl.utwente.gsd.tools;

import nl.utwente.gsd.energy.EnergyReader;
import nl.utwente.gsd.workload.Workloads;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import java.util.stream.Collectors;

/**
 * Ancillary load generator (AX3 read path, AX4 linearity, AX6 E-core
 * confinement): {@code threads} platform threads spin the CPU workload's
 * Mandelbrot kernel for {@code seconds}, and the energy counters are read once
 * before and once after, exactly as the benchmark profiler does. 0 threads is
 * an idle window.
 *
 * <p>Usage: java -cp benchmarks.jar nl.utwente.gsd.tools.LoadProbe
 * &lt;threads&gt; &lt;seconds&gt; &lt;out.json&gt;
 */
public final class LoadProbe {

    private LoadProbe() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println("usage: LoadProbe <threads> <seconds> <out.json>");
            System.exit(2);
        }
        int threads = Integer.parseInt(args[0]);
        double seconds = Double.parseDouble(args[1]);
        EnergyReader reader = EnergyReader.forThisMachine();
        Thread.sleep(2000); // let JVM start-up settle, as IdleBaseline does

        AtomicLong ops = new AtomicLong();
        long deadline = System.nanoTime() + (long) (seconds * 1e9);
        List<Thread> workers = new ArrayList<>();
        Map<String, Long> start = reader.readAll();
        long t0 = System.nanoTime();
        for (int i = 0; i < threads; i++) {
            final int offset = i;
            workers.add(Thread.ofPlatform().start(() -> {
                long sink = 0;
                while (System.nanoTime() < deadline) {
                    sink += Workloads.mandelbrotEscapes(128, offset);
                    ops.incrementAndGet();
                }
                if (sink == Long.MIN_VALUE) throw new AssertionError("unreachable");
            }));
        }
        if (threads == 0) Thread.sleep((long) (seconds * 1000));
        for (Thread w : workers) w.join();
        long t1 = System.nanoTime();
        Map<String, Long> end = reader.readAll();
        double window = (t1 - t0) / 1e9;
        reader.checkFresh(start, end, window);

        String watts = start.keySet().stream()
                .map(d -> String.format(Locale.ROOT, "\"%s\": %.6f", d,
                        reader.deltaFor(d, start.get(d), end.get(d)) / 1e6 / window))
                .collect(Collectors.joining(", "));
        String json = String.format(Locale.ROOT,
                "{\"threads\": %d, \"seconds\": %.3f, \"ops\": %d, \"start_epoch_ms\": %d, \"watts\": {%s}}%n",
                threads, window, ops.get(), System.currentTimeMillis() - Math.round(window * 1000), watts);
        Files.writeString(Path.of(args[2]), json);
        System.out.print(json);
    }
}
