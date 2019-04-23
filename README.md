**High Level Approach**

- First, we hardcoded the leader and did no log replication, in order to pass the simple tests for the milestone. 
- Then, we implemented elections in order to pass the crash tests. 
- Next, we implemented log replication for the unreliable network tests, and added batching to improve performance.
- Finally, we debugged!!! For hours.

**Challenges**
- SO MANY BUGS. Big bugs, small bugs, silly bugs, infuriating bugs. Bugs we almost cried about in public.
- The two most difficult parts of this assignment for us were 1) writing large chunks of code without being able to test, and 2) not being able to easily pinpoint the cause(s) of crashes due to the nondeterministic nature of the network tests. 
- Did this project build character? Yes. Did we survive it? Barely. 

**Testing Method**
- We tried to test on a gradient from simple to hard tests. 
- When things started working on harder tests, we'd go back to simpler ones for regression testing. The simple ones would then often start failing. 
- *What we learned*: Progress is not linear (see: building character). If we had to plot our progress for this project on a graph, it would likely resemble an unfinished Etch-A-Sketch. We went from passing 8 tests to 17 after changing one line of code. We would like to thank the Academy, and caffeine.
