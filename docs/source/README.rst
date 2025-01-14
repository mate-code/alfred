Welcome to alfred3 |zenodo|_
============================

alfred3 - a library for rapid experiment development

Alfred3 is a package for Python 3 offering experimenters in the social 
sciences a fast and easy way to create truly dynamic computer experiments 
for a wide range of applications.

Installation
------------

If you have Python 3.7 or newer installed, just install alfred3 via pip::

    $ pip3 install alfred3

A detailed step-by-step guide is available here:

A "Hello, world" experiment
---------------------------

Creating a hello-world experiment is as easy as writing this *script.py*
file. You can even do it in a simple text editor. Note that the file
must be named ``script.py``::

    import alfred3 as al
    exp = al.Experiment()
    exp += al.Page("Hello, world!", name="hello_world") 

To run the script, open a terminal and change the working directory to
your experiment directory::

    $ cd path/to/experiment

Next, simply execute the following command in the terminal::

    $ alfred3 run

If you have *Google Chrome* installed on your machine, a browser window 
with the experiment opens automatically. Otherwise, open any webbrowser 
and visit http://127.0.0.1:5000/start to start the experiment.

Of course, this "Hello, world" experiment does not contain much content:
Only a single page with a heading. To learn how to add content to an 
experiment, visit our tutorials: (to be filled)


Questions and Answers
----------------------

We use GitHub discussions: https://github.com/ctreffe/alfred/discussions/categories/q-a
You can ask questions, share ideas, and showcase your work there. Do not
hesitate to ask!

Citation
--------

.. important::

    **If you are publishing research conducted using alfred3, the 
    following citation is required:**

    Treffenstaedt, C., Brachem, J., & Wiemann, P. (2021). Alfred3 - A 
    library for rapid experiment development (Version x.x.x). Göttingen, 
    Germany: https://doi.org/10.5281/zenodo.1437219

If you want to use alfred3, please contact us via alfred@psych.uni-goettingen.de.

alfred3 Mailing List
--------------------

If you want to stay up to date with current developments, you can join 
our `mailing list`_.
We use this list to announce new releases and spread important 
information concerning the use of Alfred. You can expect to receive at 
most one mail per month.

.. |zenodo| image:: https://zenodo.org/badge/150700371.svg
.. _zenodo: https://zenodo.org/badge/latestdoi/150700371
.. _mailing list: https://listserv.gwdg.de/mailman/listinfo/Alfred