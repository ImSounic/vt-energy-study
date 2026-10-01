package nl.utwente.gsd.energy;

import java.io.IOException;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Reads Apple Silicon energy counters (IOReport "Energy Model" group) through
 * the native shim in harness/native, called via the FFM API.
 *
 * <p>Counters are read on demand only, at iteration boundaries. On macOS 27
 * they are published only while a privileged sampler (powermetrics) runs, so
 * each reading lags real time by at most one powermetrics interval; the
 * experiment scripts keep powermetrics running at 100 ms.
 *
 * <p>Channel hierarchy (verified on M4, macOS 27; do not double-count):
 * CPU_Energy = ECPU + PCPU; ECPU = ECPU0..5 + ECPM; PCPU = PCPU0..3 + PCPM.
 * GPU (mJ, frozen without powermetrics) and GPU_Energy (nJ, always live) are
 * different meters. Resolution is 1 mJ for mJ channels. Not thread-safe
 * (one shared native buffer); JMH calls profilers from a single thread.
 */
public final class IoReportReader implements EnergyReader {

    static final String LIB_PROPERTY = "vt.ioreport.lib";
    private static final String LIB_FILE = "libioreport_shim.dylib";
    private static final int NAME_LEN = 64; // matches NAME_LEN in ioreport_shim.c

    /** Canary channel: while powermetrics refreshes, it advances by tens of mJ or more per 0.5 s even at idle. */
    static final String CANARY = "CPU_Energy";
    static final double MIN_CHECK_SECONDS = 0.5;

    private final MethodHandle read;
    private final List<String> names = new ArrayList<>();
    private final MemorySegment buffer;

    public IoReportReader() throws IOException {
        Path lib = locateLibrary();
        MethodHandle readHandle;
        try {
            Linker linker = Linker.nativeLinker();
            SymbolLookup symbols = SymbolLookup.libraryLookup(lib, Arena.global());
            MethodHandle open = linker.downcallHandle(symbols.find("ior_open").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT));
            MethodHandle name = linker.downcallHandle(symbols.find("ior_name").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT, ValueLayout.ADDRESS, ValueLayout.JAVA_INT));
            readHandle = linker.downcallHandle(symbols.find("ior_read").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS, ValueLayout.JAVA_INT));
            int n = (int) open.invokeExact();
            if (n <= 0) throw new IOException("IOReport shim found no energy channels (code " + n + ")");
            try (Arena arena = Arena.ofConfined()) {
                MemorySegment buf = arena.allocate(NAME_LEN);
                for (int i = 0; i < n; i++) {
                    int rc = (int) name.invokeExact(i, buf, NAME_LEN);
                    if (rc != 0) throw new IOException("ior_name failed for channel " + i);
                    names.add(uniqueKey(buf.getString(0).replace(' ', '_')));
                }
            }
        } catch (IOException e) {
            throw e;
        } catch (Throwable t) {
            throw new IOException("IOReport shim call failed", t);
        }
        this.read = readHandle;
        this.buffer = Arena.global().allocate(ValueLayout.JAVA_LONG, names.size());
    }

    private String uniqueKey(String base) {
        String key = base;
        for (int i = 2; names.contains(key); i++) key = base + "#" + i;
        return key;
    }

    @Override
    public Map<String, Long> readAll() throws IOException {
        int got;
        try {
            got = (int) read.invokeExact(buffer, names.size());
        } catch (Throwable t) {
            throw new IOException("ior_read failed", t);
        }
        if (got != names.size()) throw new IOException("ior_read returned " + got);
        Map<String, Long> out = new LinkedHashMap<>();
        for (int i = 0; i < names.size(); i++) {
            long v = buffer.getAtIndex(ValueLayout.JAVA_LONG, i);
            if (v < 0) throw new IOException("channel missing from sample: " + names.get(i));
            out.put(names.get(i), v);
        }
        return out;
    }

    @Override
    public long deltaFor(String domain, long start, long end) {
        if (!names.contains(domain)) throw new IllegalArgumentException("unknown channel: " + domain);
        return delta(start, end);
    }

    @Override
    public void checkFresh(Map<String, Long> start, Map<String, Long> end, double seconds) {
        checkFresh(start.get(CANARY), end.get(CANARY), seconds);
    }

    static void checkFresh(Long start, Long end, double seconds) {
        if (seconds >= MIN_CHECK_SECONDS && start != null && start.equals(end)) {
            throw new IllegalStateException(String.format(Locale.ROOT,
                    "%s unchanged over %.2f s: IOReport counters are frozen; is 'sudo powermetrics' running?",
                    CANARY, seconds));
        }
    }

    /** 64-bit cumulative counters do not wrap in practice; a decrease means a reset. */
    static long delta(long start, long end) {
        if (end < start) {
            throw new IllegalStateException("IOReport counter went backwards: " + start + " -> " + end);
        }
        return end - start;
    }

    /** -Dvt.ioreport.lib if set, else the nearest native/ dir above the jar or classes dir. */
    static Path locateLibrary() throws IOException {
        String explicit = System.getProperty(LIB_PROPERTY);
        if (explicit != null) {
            Path p = Path.of(explicit);
            if (!Files.isRegularFile(p)) throw new IOException("not a file: " + p);
            return p;
        }
        try {
            Path here = Path.of(IoReportReader.class.getProtectionDomain().getCodeSource().getLocation().toURI());
            for (Path dir = here; dir != null; dir = dir.getParent()) {
                Path candidate = dir.resolve("native").resolve(LIB_FILE);
                if (Files.isRegularFile(candidate)) return candidate;
            }
        } catch (URISyntaxException | SecurityException e) {
            // fall through to the error below
        }
        throw new IOException(LIB_FILE + " not found; run harness/native/build.sh or set -D" + LIB_PROPERTY);
    }
}
