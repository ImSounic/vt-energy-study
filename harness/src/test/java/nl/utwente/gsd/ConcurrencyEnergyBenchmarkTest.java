package nl.utwente.gsd;

import nl.utwente.gsd.concurrency.ExecutionStrategy;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ConcurrencyEnergyBenchmarkTest {

    @Test
    void virtualThreadsAcceptMatchingCarrierCount() {
        assertDoesNotThrow(() ->
                ConcurrencyEnergyBenchmark.checkCarrierCount(ExecutionStrategy.VIRTUAL_THREADS, 8, "8"));
    }

    @Test
    void virtualThreadsRejectMissingCarrierCount() {
        assertThrows(IllegalStateException.class, () ->
                ConcurrencyEnergyBenchmark.checkCarrierCount(ExecutionStrategy.VIRTUAL_THREADS, 8, null));
    }

    @Test
    void virtualThreadsRejectMismatchedCarrierCount() {
        assertThrows(IllegalStateException.class, () ->
                ConcurrencyEnergyBenchmark.checkCarrierCount(ExecutionStrategy.VIRTUAL_THREADS, 8, "4"));
    }

    @Test
    void otherConstructsIgnoreTheCarrierProperty() {
        assertDoesNotThrow(() ->
                ConcurrencyEnergyBenchmark.checkCarrierCount(ExecutionStrategy.FIXED_POOL, 8, null));
        assertDoesNotThrow(() ->
                ConcurrencyEnergyBenchmark.checkCarrierCount(ExecutionStrategy.SEQUENTIAL, 1, "16"));
    }

    @Test
    void socketPortIsRequired() {
        assertThrows(IllegalStateException.class, () -> ConcurrencyEnergyBenchmark.socketPort(null));
        assertEquals(47000, ConcurrencyEnergyBenchmark.socketPort(47000));
    }
}
