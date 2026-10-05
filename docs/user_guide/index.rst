.. _user-guide:

**********
User Guide
**********
The Loop step runs the steps in its body repeatedly: once for each value of a
variable, each item in a list, each row of a table, or each structure in the
database.

Types of loops
==============
For
   A variable runs from a start to an end value by a step, e.g. ``i`` from 1 to
   10. Each iteration runs in a directory named after the value,
   ``iter_01``, ``iter_02``, ...
Foreach
   A variable takes each of a list of values in turn, e.g. SMILES strings or
   Hamiltonians.
For rows in table
   The body runs once for each row of a table, or each row matching a criterion.
   The row is the table's current row during the iteration, so steps can read
   and write its cells; with "Values as variables" each cell is also a variable.
   The rows are chosen when the loop starts: rows the body appends are not
   looped over.
For systems in the database
   The body runs once for each structure chosen by the standard structure
   selection (by default every system, with its last configuration), which is
   the current system and configuration during the iteration. Directories may
   be named after the systems or configurations.

Errors
======
"On errors" says what happens when a step in the body fails: continue with the
next iteration (the default), leave the loop and carry on with the rest of the
flowchart, or stop the job.

Restarting
==========
A job stopped part way through a loop (killed, out of time) resumes in the
iteration it was in, at the step that had not finished, when rerun with
``--resume``; the JobServer does this for you. Finished iterations are not run
again.

.. _parallel-iterations:

Running iterations in parallel
==============================
With "Run iterations in parallel" set to yes, the iterations run at the same
time, each in an evaluator of its own, and what they did is brought back into
the job afterwards. This is worthwhile when each iteration does a substantial
calculation: starting an evaluator takes about five seconds, so for iterations
of a few seconds a serial loop is as fast or faster.

The contract
------------
Choosing parallel declares that the iterations are independent:

- Each iteration sees the job's database as it was when the loop started. An
  iteration does not see what another one does, even an earlier one. (A file in
  the job's directory that an iteration reads, but has not written itself, is
  read as it is at that moment.)
- What comes back, merged in iteration order: new and changed structures
  (systems and configurations, with new ids), the current configuration of a
  system, properties, table rows (appended after those of the iterations
  before, as serially) and cells, new tables and columns, and files written in
  the job's directory
  (``/name``). Files a step appends to, such as a structure file written by
  Write Structure in append mode, get each iteration's part in order; other
  files are those of the last iteration that wrote them, as for a serial loop;
  a table saved inside the loop is saved again after the merge.
- Variables set in the body are not visible after the loop.
- ``break``, ``continue`` and skipping an iteration work as in a serial loop:
  after a break in iteration *k* the iterations after *k* are not merged, so
  the result is the serial one.
- A failed iteration is never merged (a serial loop keeps what a failed
  iteration wrote before it failed). With "continue" it is reported and the
  loop goes on; with "exit the loop" the iterations after it are not merged;
  with "stop the job" the job fails, and resuming it runs the failed iteration
  again.

A loop whose iterations build on each other -- each reading a table row or a
structure an earlier iteration wrote, or overwriting the current structure that
an earlier iteration created -- gives a different result in parallel. Read
Structure's "Create a new system and configuration" keeps such iterations
independent.

Settings
--------
These appear when "Run iterations in parallel" is yes.

Iterations at once
   How many iterations run at the same time on this machine. By default as
   many as the cores and memory allow, given the cores and memory per iteration.
Cores per iteration
   The cores each iteration's calculations use (default 1).
Memory per iteration
   The most memory an iteration needs (default 2 GB), so that the iterations
   running together fit in the machine's memory.
Time per iteration
   An estimate of an iteration's time, used to bundle iterations into queue
   jobs when the job's calculations go to a queue.
Each iteration gets
   *selected structures* (the default): the structure the iteration works on (a
   loop over systems) and the current one, with all the tables. *Whole
   database*: a copy of the whole database, for a body that reads other
   structures. Every iteration's copy is written when the loop starts, so a
   long loop over a large database needs that much disk space.
Calculations run
   *inline* (the default): each iteration's calculations run in its own share
   of the machine. *Separate tasks* (experimental, not yet tested on a cluster):
   they go to the job's target like any job's.
Two iterations writing one table cell
   Two iterations changing the same thing that existed before the loop -- a
   cell of a table row, or a structure: its atoms' coordinates, velocities or
   other values, or the structure itself -- are an error by default; the
   alternative keeps the later iteration's change, with a warning in the
   output. For example, a loop over methods that each optimize the current
   structure in place is an error unless the later iteration may win.

Where things are
----------------
Each iteration's step directories are where a serial loop puts them,
``<loop>/<iteration>/<step>``. The iteration's own files -- its output
(``job.out``), its copy of the database and any job-level files it wrote -- are
in ``<loop>/<iteration>/_evaluator/``, which is kept for checking or debugging.

Restarting a parallel loop
--------------------------
A job stopped while its parallel loop runs resumes it: iterations already merged
are not run again, finished ones are merged, and running ones resume from their
own checkpoints. An iteration whose evaluator was killed while the job ran on
(out of memory, say) is run again, resuming where it was, up to twice.

Index
=====

* :ref:`genindex`
