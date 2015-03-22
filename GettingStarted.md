Unlike many methods in population genetics, ∂a∂i is more than just a single command-line program. This allows us to offer more features (such as [plotting](http://dadi.googlecode.com/svn/trunk/doc/api/dadi.Plotting-module.html)) and allows you greater flexibility. On the other hand, it may require adjusting to a new workflow and getting a little comfortable with Python.

Luckily, Python is very easy to read, and you can probably learn most of what you need just by looking at the [examples](http://code.google.com/p/dadi/source/browse/#svn/trunk/examples) provided in the source distribution of dadi. If you'd like to dig more into Python, there are many good [tutorials](http://docs.python.org/tutorial/) and [books](http://oreilly.com/catalog/9780596513986/).

To get your feet wet, start with the [YRI\_CEU example](http://code.google.com/p/dadi/source/browse/#svn/trunk/examples/YRI_CEU), which fits a model to EGP data from the YRI and CEU populations.

One important tip is to take advantage of Python's interactivity. My preferred workflow involves one window editing a Python script (e.g. `script.py`) and another running an IPython session. In the IPython session I can interactively use ∂a∂i to explore my data, while I record my work in `script.py`. IPython's `%run script.py` magic command lets me apply changes I've made to `script.py` to my interactive session. (Note that you will need to [reload](http://docs.python.org/tutorial/modules.html) other Python used by your script if you change them.) Once I'm sure I've defined my model correctly and have a useful script, I run that from the command line (`python script.py`) for extended optimizations and other long computations.