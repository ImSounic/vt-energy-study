# Presentation script, Assignment 1 (16 September 2026, 9-minute cap)

Total target: 8:35. Slides 1 to 5 about 4:20, slides 6 to 9 about 4:15.
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

## Slide 6, Methodology (1:15)
The experiment in one sentence: we give Java the same pile of work four times, using four different ways of handing it to the processor, and we measure how much electricity each way uses.

The four ways are the constructs. Think of a kitchen with 256 orders. Platform threads: one chef per order, expensive, and most of them stand around waiting. A fixed pool: eight chefs, orders queue up. Fork/Join: eight chefs who steal orders from a busy colleague when they run out. Virtual threads: 256 orders in progress but only a few real chefs; when an order goes into the oven, the chef puts it down and picks up another. The first three are what Fernando measured in 2014. The fourth arrived in 2023.

We test two kinds of work, because the constructs are built for different kinds. CPU-bound is pure computation, constant chopping. I/O-bound is mostly waiting, the order sits in the oven. Virtual threads are designed for waiting, so testing only one kind would either flatter them or punish them unfairly.

We sweep the number of workers to reproduce the 2014 curve, and we run everything unpinned and then pinned to each core type. The machine has six performance, eight efficient and two low-power cores. An Apple M4 tells us whether our findings are Intel-specific.

## Slide 7, How we measure (1:10)
Three components. RAPL is the energy meter Intel builds into the processor for its own power management. Linux exposes it as a file: read it before, read it after, subtract, and you have the joules consumed. JMH is the standard Java benchmark harness: a fresh JVM per run, warm-up before measurement so the JIT compiler has finished, and averages with confidence intervals. Our profiler connects the two: it reads the counters once at the start and once at the end of every measured iteration and reports joules per operation next to milliseconds per operation.

Readings are comparable because everything else is held fixed. Same machine on mains power, nothing else running, identical JVM settings. Warm-up every time. And the same list of 256 tasks for all four constructs, so the only thing that changes is how the work is dispatched.

Two details matter. We never poll the counters, because polling keeps the processor awake and inflates the numbers by tens of watts. And we correct for counter wraparound; a well-known language-energy paper got negative energy readings by not doing that. [cut if over time: the last sentence]

## Slide 8, Feasibility (1:20)
We have already built and run the full pipeline. This is a small test on our laptop: the I/O-bound workload, pools capped at eight workers, all four constructs.

Read the table row by row. The fixed pool and Fork/Join took about 320 milliseconds. Eight workers, 256 tasks, each waiting 10 milliseconds: every worker does 32 in a row, 32 times 10 is 320. We measured 323.5. Virtual threads took 10 milliseconds, because all 256 waited at the same time. Platform threads took 19, all at once as well, but creating 256 real threads costs more than creating 256 virtual ones.

So virtual threads used 27 times less energy. That is not a discovery, and we are careful about it. With the pool capped at eight and tasks that only wait, the pool must be slow and virtual threads must be fast. We could have predicted the 320 before running anything. The reason to show it is that we predicted 320 and measured 323.5: the pipeline measures correctly. Think of it as calibrating the scale before weighing anything.

The genuinely interesting column is the last one. Virtual threads drew more power, 14 watts against 12, but finished 31 times sooner, so they used far less energy overall. Faster used more power per second and less energy in total. In 2014 the opposite pattern often held. Whether faster means greener depends on the construct, the workload and the hardware, and mapping that out is the full experiment.

## Slide 9, Conclusion (0:30)
Problem: never measured. Approach: four constructs, two workloads, controlled core placement, real energy counters, pipeline built. Assignment 2 finalizes the design; Assignment 3 executes it and publishes a replication package. Every outcome is informative: the 2014 result confirmed, overturned, or bounded. Thank you, we welcome your questions.

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
