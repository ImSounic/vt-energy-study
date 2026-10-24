package nl.utwente.gsd.workload;

import nl.utwente.gsd.concurrency.ExecutionStrategy;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.net.InetAddress;
import java.net.Socket;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class SocketDelayServerTest {

    private SocketDelayServer server;

    @BeforeEach
    void start() throws Exception {
        assertListenBacklogFits256();
        server = SocketDelayServer.start(0, 10);
    }

    /** macOS caps the listen backlog at kern.ipc.somaxconn (default 128): 256 simultaneous connects are reset. */
    private static void assertListenBacklogFits256() throws Exception {
        if (!System.getProperty("os.name").toLowerCase(java.util.Locale.ROOT).contains("mac")) return;
        Process p = new ProcessBuilder("sysctl", "-n", "kern.ipc.somaxconn").start();
        int somaxconn = Integer.parseInt(new String(p.getInputStream().readAllBytes()).trim());
        assertTrue(somaxconn >= 256, "kern.ipc.somaxconn=" + somaxconn
                + " < 256 resets SOCKET connections; run: sudo sysctl kern.ipc.somaxconn=1024");
    }

    @AfterEach
    void stop() throws Exception {
        server.close();
    }

    @Test
    void oneRoundTripTakesAtLeastTheDelay() {
        Runnable task = Workloads.socket(1, server.port()).get(0);
        long start = System.nanoTime();
        task.run();
        long elapsedMillis = (System.nanoTime() - start) / 1_000_000;
        assertTrue(elapsedMillis >= 10, "round trip took " + elapsedMillis + " ms");
        assertEquals(1, server.requests());
    }

    @Test
    void replyHas64Bytes() throws Exception {
        try (Socket s = new Socket(InetAddress.getLoopbackAddress(), server.port())) {
            s.getOutputStream().write(new byte[64]);
            InputStream in = s.getInputStream();
            assertEquals(64, in.readNBytes(64).length);
            assertEquals(-1, in.read(), "server must close after its reply");
        }
    }

    @Test
    void handles256ConcurrentClients() throws Exception {
        List<Runnable> tasks = Workloads.socket(256, server.port());
        long start = System.nanoTime();
        ExecutionStrategy.VIRTUAL_THREADS.execute(tasks, 0);
        long elapsedMillis = (System.nanoTime() - start) / 1_000_000;
        assertTrue(elapsedMillis < 2000, "256 concurrent round trips took " + elapsedMillis + " ms");
        assertEquals(256, server.requests());
    }

    /** SO_LINGER 0 closes with RST, so no client port lingers in TIME_WAIT (A3-D4). */
    @Test
    void repeatedOperationsDoNotExhaustPorts() throws Exception {
        List<Runnable> tasks = Workloads.socket(256, server.port());
        for (int i = 0; i < 20; i++) {
            ExecutionStrategy.VIRTUAL_THREADS.execute(tasks, 0);
        }
        assertEquals(20 * 256, server.requests());
    }

    @Test
    void socketTaskFailsLoudlyWhenNoServerListens() throws Exception {
        int port = server.port();
        server.close();
        Runnable task = Workloads.socket(1, port).get(0);
        assertThrows(RuntimeException.class, task::run);
    }
}
