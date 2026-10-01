package nl.utwente.gsd.energy;

import org.openjdk.jmh.profile.ProfilerException;

import java.io.IOException;

/**
 * Apple IOReport energy per iteration. Requires powermetrics running as root:
 * on macOS 27 it is what refreshes the counters.
 * Register with: -prof nl.utwente.gsd.energy.IoReportProfiler
 */
public class IoReportProfiler extends EnergyProfiler {

    public IoReportProfiler() throws ProfilerException {
        super(open(), "ioreport");
    }

    private static IoReportReader open() throws ProfilerException {
        try {
            return new IoReportReader();
        } catch (IOException e) {
            throw new ProfilerException(
                "Cannot initialise IOReport: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Apple IOReport energy per iteration (refreshed by powermetrics)";
    }
}
