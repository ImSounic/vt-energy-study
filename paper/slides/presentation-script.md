# Presentation script, Assignment 1 (16 September 2026, 9-minute cap)

Total target: 7:30. Slides 1 to 5 about 4:20, slides 6 to 9 about 3:10.
Lines marked [cut if over time] are the first to drop.

## Slide 1, Title (0:10)
We are proposing an energy study of how Java runs threads, on the kind of processor most laptops now have.

## Slide 2, Background (1:05)
In 2014, Fernando's group measured three ways of running threads in Java. In six of nine benchmarks the single-threaded version used the least energy. Their conclusion: being faster has little correlation with being greener. Two things changed since. Java 21 added virtual threads: thousands of lightweight threads over a few real ones, and a thread that blocks steps aside. And processors went hybrid: performance cores and efficiency cores on one chip, which the Java scheduler cannot tell apart.

## Slide 3, The problem (0:55)
Nobody has measured virtual threads against the established constructs for energy, and nobody has measured any of them on a hybrid processor. The 2014 study predates both. The only hybrid-processor JVM study examines garbage collection, not application threads. And the only virtual-thread energy paper describes a configuration that cannot execute as reported. Developers choose today without data.

## Slide 4, Why it matters (1:05)
Data centres used 415 terawatt-hours in 2024, 1.5 percent of global electricity, projected to double by 2030, and Java runs a substantial share of that. There is a cost dimension and a battery dimension. Virtual threads make concurrent code considerably simpler, which is good for developers, but simpler may mean more threads, more active cores, more energy. That is the tension. And the literature disagrees on whether faster means greener; the strongest yes study says hybrid processors may differ. That is our platform.

## Slide 5, Goal and questions (1:05)
Our goal is to characterize the energy of the four constructs and its relationship to time, on hybrid processors, from a developer's perspective. Three specific goals: does the 2014 result still hold; where do virtual threads stand for CPU-bound versus I/O-bound work; and does the core type the work lands on change its energy cost, and how much does the scheduler forgo by not knowing.

[Handoff to second presenter]

## Slide 6, Methodology (0:55)
We give Java the same work four times, dispatched four different ways, and measure the electricity each way uses. The four ways are the constructs: one thread per task, a fixed pool of workers, Fork/Join with work stealing, and virtual threads, where a thread that waits steps aside so a real thread can run something else. The first three are what Fernando measured in 2014; the fourth arrived in 2023.

Two kinds of work, because the constructs are built for different kinds: CPU-bound, pure computation, and I/O-bound, mostly waiting. Virtual threads are designed for waiting, so testing only one kind would bias the result. We sweep the number of workers to reproduce the 2014 curve, and we run everything unpinned and then pinned to each core type: six performance, eight efficient, two low-power cores. An Apple M4 checks whether findings are Intel-specific.

## Slide 7, How we measure (0:50)
RAPL is the energy meter Intel builds into the processor. Linux exposes it as a file: read before, read after, subtract, and you have the joules. JMH is the standard Java benchmark harness: fresh JVM per run, warm-up so the JIT has finished, confidence intervals. Our profiler reads the counters once at the start and once at the end of each measured iteration, and reports joules per operation next to milliseconds per operation.

Readings are comparable because everything else is fixed: same machine on mains power, nothing else running, identical JVM settings, warm-up every time, and the same 256 tasks for all four constructs. We never poll the counters, because polling keeps the processor awake and inflates the numbers.

## Slide 8, Feasibility (1:00)
The pipeline is built and has run. This is a small test: I/O-bound workload, pools capped at eight workers, all four constructs.

The pools took about 320 milliseconds: eight workers, 256 tasks, 10 milliseconds each, so 32 in a row per worker. Virtual threads took 10, because all 256 waited at once. So virtual threads used 27 times less energy. That is expected, not a discovery: with the pool capped and tasks that only wait, it had to come out this way. The point is that we predicted 320 and measured 323.5. The pipeline measures correctly.

The interesting column is the last one. Virtual threads drew more power, 14 watts against 12, but finished so much sooner that they used far less energy overall. Faster used more power and less energy. In 2014 the opposite often held. Which one wins depends on construct, workload and hardware, and mapping that is the full study.

## Slide 9, Conclusion (0:25)
Problem: never measured. Approach: four constructs, two workloads, controlled core placement, real energy counters, pipeline built. Assignment 2 finalizes the design; Assignment 3 runs it and publishes a replication package. Every outcome is informative. Thank you, we welcome your questions.

---

# Prepared answers for the Commenter group

**Is the 27x real?**
It is expected by construction. Eight workers on 256 waiting tasks must take at least 320 milliseconds; we measured 323.5. The value of the pilot is that it proves the instrument works, not that virtual threads win.

**If virtual threads win, why do the study?**
Because this was a waiting-heavy workload with the pool deliberately capped. On CPU-bound work virtual threads have nothing to gain, and once we set the number of real threads underneath them explicitly, the comparison changes completely. The pilot shows the instrument works; it does not answer the question.

**Is the comparison fair to virtual threads, or to the pools?**
The parallelism setting means different things per construct: a pool of eight has eight threads; virtual threads ignore it and create one per task. We know this, we say it on the feasibility slide, and Assignment 2 controls it by setting the carrier thread count explicitly with jdk.virtualThreadScheduler.parallelism, and pins placement with taskset.

**What is RAPL, and is it accurate?**
Running Average Power Limit: the processor's built-in energy counters, kept for its own power management, readable by software for free. It is a hardware model rather than a physical meter, but it has been validated against external meters in the literature and is the standard instrument for Intel machines in this course. It does not see the display, disk or network separately; that scope will be stated in Assignment 2.

**Why not a wall-plug meter?**
RAPL resolves per-iteration windows that a wall meter cannot attribute to a specific run, costs nothing, and is validated. A wall-meter cross-check is a reasonable addition for Assignment 3.

**Why do you call the 2026 paper unreliable evidence?**
It reports OpenJDK 21 with ZGC running on a 32-bit microcontroller with 192 kilobytes of memory. ZGC is a 64-bit-only collector and HotSpot has no port for that chip, so the configuration cannot execute as reported. Whatever they measured, it was not what they describe. It also compares only two arms, so even a corrected version would not cover our comparison.

**Thread.sleep is not real I/O.**
Agreed. Sleep is a genuine blocking call that makes a virtual thread unmount, which is the mechanism we study, and it gives us an exactly controlled latency. Assignment 2 adds a real-socket workload to address the external validity threat.

**Isn't measuring the system changing the system?**
Yes, which is why we do not poll. Two counter reads per iteration add nothing measurable; polling at high frequency keeps the CPU out of deep sleep states and inflates idle power.
