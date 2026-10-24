package nl.utwente.gsd.workload;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.ByteBuffer;
import java.nio.channels.SelectionKey;
import java.nio.channels.Selector;
import java.nio.channels.ServerSocketChannel;
import java.nio.channels.SocketChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Iterator;
import java.util.Locale;
import java.util.PriorityQueue;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Loopback server of the SOCKET workload: reads a {@link Workloads#SOCKET_PAYLOAD}-byte
 * request, replies with as many bytes {@code delay} ms later, then closes.
 *
 * <p>A single thread runs one NIO selector and a timer queue, so a pending reply
 * blocks no thread and the server's own behavior is identical for every
 * construct under test. It runs in its own JVM, started by the orchestrator once
 * per batch, so its energy is a constant overhead that the idle baselines and
 * the server-only run quantify.
 *
 * <p>Usage: java -cp benchmarks.jar nl.utwente.gsd.workload.SocketDelayServer
 * &lt;port&gt; &lt;delayMs&gt; [stats.json]. Prints {@code READY <port>} once
 * listening; on SIGTERM writes request count and process CPU time.
 */
public final class SocketDelayServer implements AutoCloseable {

    private record Due(long atNanos, SocketChannel channel) {}

    private static final int BACKLOG = 1024;

    private final ServerSocketChannel listener;
    private final Selector selector;
    private final long delayNanos;
    private final PriorityQueue<Due> pending = new PriorityQueue<>((a, b) -> Long.compare(a.atNanos, b.atNanos));
    private final AtomicLong requests = new AtomicLong();
    private final Thread loop;
    private volatile boolean running = true;

    private SocketDelayServer(int port, int delayMillis) throws IOException {
        this.delayNanos = delayMillis * 1_000_000L;
        this.selector = Selector.open();
        this.listener = ServerSocketChannel.open();
        listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(), port), BACKLOG);
        listener.configureBlocking(false);
        listener.register(selector, SelectionKey.OP_ACCEPT);
        this.loop = new Thread(this::run, "socket-delay-server");
        loop.setDaemon(true);
    }

    /** Binds to 127.0.0.1:{@code port} (0 = ephemeral) and starts the selector thread. */
    public static SocketDelayServer start(int port, int delayMillis) throws IOException {
        SocketDelayServer server = new SocketDelayServer(port, delayMillis);
        server.loop.start();
        return server;
    }

    public int port() {
        return listener.socket().getLocalPort();
    }

    /** Complete requests received so far (each is answered after the delay). */
    public long requests() {
        return requests.get();
    }

    private void run() {
        try {
            while (running) {
                long timeoutMillis = 0; // 0 = block until a selector event
                Due next = pending.peek();
                if (next != null) {
                    long waitNanos = next.atNanos - System.nanoTime();
                    // Round up so that a reply is never sent before its delay has elapsed.
                    timeoutMillis = Math.max(1, (waitNanos + 999_999) / 1_000_000);
                }
                selector.select(timeoutMillis);
                Iterator<SelectionKey> keys = selector.selectedKeys().iterator();
                while (keys.hasNext()) {
                    SelectionKey key = keys.next();
                    keys.remove();
                    if (!key.isValid()) continue;
                    if (key.isAcceptable()) accept();
                    else if (key.isReadable()) read(key);
                }
                replyDue();
            }
        } catch (IOException e) {
            if (running) throw new IllegalStateException("socket delay server failed", e);
        }
    }

    private void accept() throws IOException {
        SocketChannel client;
        while ((client = listener.accept()) != null) {
            client.configureBlocking(false);
            client.register(selector, SelectionKey.OP_READ, ByteBuffer.allocate(Workloads.SOCKET_PAYLOAD));
        }
    }

    private void read(SelectionKey key) throws IOException {
        SocketChannel client = (SocketChannel) key.channel();
        ByteBuffer request = (ByteBuffer) key.attachment();
        int n;
        try {
            n = client.read(request);
        } catch (IOException e) {
            client.close(); // client reset before its request was complete
            return;
        }
        if (n < 0) {
            client.close();
            return;
        }
        if (!request.hasRemaining()) {
            key.interestOps(0);
            requests.incrementAndGet();
            pending.add(new Due(System.nanoTime() + delayNanos, client));
        }
    }

    private void replyDue() {
        long now = System.nanoTime();
        while (!pending.isEmpty() && pending.peek().atNanos <= now) {
            SocketChannel client = pending.poll().channel;
            try (client) {
                ByteBuffer reply = ByteBuffer.allocate(Workloads.SOCKET_PAYLOAD);
                // A 64-byte write into an empty socket buffer completes at once;
                // the bound only guards against a pathological peer.
                for (int attempts = 0; reply.hasRemaining() && attempts < 1000; attempts++) {
                    client.write(reply);
                }
            } catch (IOException e) {
                // the client gave up (reset); nothing to reply to
            }
        }
    }

    @Override
    public void close() throws IOException {
        running = false;
        selector.wakeup();
        try {
            loop.join(5_000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        for (Due due : pending) due.channel.close();
        listener.close();
        selector.close();
    }

    static String statsJson(int port, int delayMillis, long requests, double cpuSeconds, double uptimeSeconds) {
        return String.format(Locale.ROOT,
                "{\"port\": %d, \"delay_ms\": %d, \"requests\": %d, \"cpu_s\": %.3f, \"uptime_s\": %.3f}%n",
                port, delayMillis, requests, cpuSeconds, uptimeSeconds);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || args.length > 3) {
            System.err.println("usage: SocketDelayServer <port> <delayMs> [stats.json]");
            System.exit(2);
        }
        int delayMillis = Integer.parseInt(args[1]);
        long t0 = System.nanoTime();
        SocketDelayServer server = start(Integer.parseInt(args[0]), delayMillis);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            double cpu = ProcessHandle.current().info().totalCpuDuration()
                    .map(Duration::toNanos).orElse(-1L) / 1e9;
            String json = statsJson(server.port(), delayMillis, server.requests(), cpu, (System.nanoTime() - t0) / 1e9);
            System.out.print(json);
            if (args.length == 3) {
                try {
                    Files.writeString(Path.of(args[2]), json);
                } catch (IOException e) {
                    System.err.println("could not write " + args[2] + ": " + e.getMessage());
                }
            }
        }));
        System.out.println("READY " + server.port());
        System.out.flush();
        server.loop.join();
    }
}
