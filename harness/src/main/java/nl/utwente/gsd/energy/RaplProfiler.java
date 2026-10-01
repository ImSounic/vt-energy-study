package nl.utwente.gsd.energy;

import org.openjdk.jmh.profile.ProfilerException;

import java.io.IOException;

/**
 * Intel RAPL energy per iteration (Linux powercap sysfs).
 * Register with: -prof nl.utwente.gsd.energy.RaplProfiler
 */
public class RaplProfiler extends EnergyProfiler {

    public RaplProfiler() throws ProfilerException {
        super(open(), "rapl");
    }

    private static RaplReader open() throws ProfilerException {
        try {
            return new RaplReader();
        } catch (IOException e) {
            throw new ProfilerException(
                "Cannot initialise RAPL: " + e.getClass().getSimpleName() + ": " + e.getMessage());
        }
    }

    @Override
    public String getDescription() {
        return "Intel RAPL energy per iteration (powercap sysfs)";
    }
}
