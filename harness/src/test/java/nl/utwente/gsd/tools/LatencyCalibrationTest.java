package nl.utwente.gsd.tools;

import nl.utwente.gsd.workload.SocketDelayServer;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class LatencyCalibrationTest {

    @Test
    void summaryOfKnownSample() {
        Map<String, Double> s = LatencyCalibration.summarize(new double[]{4, 1, 3, 2, 5});
        assertEquals(5.0, s.get("n"));
        assertEquals(3.0, s.get("mean"));
        assertEquals(3.0, s.get("median"));
        assertEquals(5.0, s.get("max"));
        assertEquals(1.0, s.get("min"));
    }

    @Test
    void sleepsLastAtLeastTheRequestedTime() throws Exception {
        for (boolean virtual : new boolean[]{false, true}) {
            double[] ms = LatencyCalibration.sleeps(20, 1, virtual);
            assertEquals(20, ms.length);
            assertTrue(LatencyCalibration.summarize(ms).get("min") >= 1.0, "virtual=" + virtual);
        }
    }

    @Test
    void socketRoundTripsIncludeTheServerDelay() throws Exception {
        try (SocketDelayServer server = SocketDelayServer.start(0, 5)) {
            double[] ms = LatencyCalibration.roundTrips(10, server.port());
            assertTrue(LatencyCalibration.summarize(ms).get("min") >= 5.0);
        }
    }
}
