=======
History
=======
2024.7.30 -- Further improving naming of loop subdirectories
   * For loops now use the value of loop index as the subdirectory
   * Improved handling of lists for ForEach loops so blank-deliminated lists work
     properly. Quotes can be used for values with embedded blanks, much like the Linux
     commandline.
     
2024.7.28 -- Improved naming of loop subdirectories
   * The subdirectories now start at 1, not 0, to make counting more normal
   * When looping over systems, now have the option to name the directories
     after the system or configuration name, not the iteration number.
     
2023.11.9 -- Bugfix: "For" loops could crash
   * For loops could crash writing to write final_structure.mmcif before the directory
     had been made.
     
2023.10.30 -- Improved consistency of printing loop information

2023.4.24 -- Better support for rerunning/restarting jobs
    * Remove 'iteration.out' if it already exists.
      
2023.2.15 -- Starting to add loops over structures in the database

* Reorganized the documentation and changed to the standard MolSSI theme.

2022.1.16 -- Improved error handling

* Wrote the traceback for any errors caught to item_nnn/stderr.out to aid debugging.

2021.12.21 -- Cleaned up the printing

2021.12.12 -- Error handling and querying for loops over tables

* Errors in the body of the loop are caught and can be ignored or handled in different
  ways at the direction of the user.
* When looping over rows in a table, a query can be used to select the rows to operate
  on.

2021.10.13 -- updated to Python 3.8 and 3.9

2021.6.3 -- updated for internal changes in argument parsing

2021.2.11 (11 February 2021)
----------------------------

* Updated the README file to give a better description.
* Updated the short description in setup.py to work with the new installer.
* Added keywords for better searchability.

2021.2.4 (4 February 2021)
--------------------------

* Updated for compatibility with the new system classes in MolSystem
  2021.2.2 release.

2020.12.4 (4 December 2020)
---------------------------

* Internal: switching CI from TravisCI to GitHub Actions, and in the
  process moving documentation from ReadTheDocs to GitHub Pages where
  it is consolidated with the main SEAMM documentation.

2020.11.2 (2 November 2020)
---------------------------

* Updated to be compatible with the new command-line argument
  handling.

2020.10.1 (1 October 2020)
--------------------------

* Bugfix: fixed a blocking bug in handling of periodic system.

2020.9.25.1 (25 September 2020)
-------------------------------

* Internal: added a missed installation requirement.

2020.9.25 (25 September 2020)
-----------------------------

* Updated to be compatible with the new system classes in MolSystem.

2020.8.3 (3 August 2020)
------------------------

* Bugfix: corrected problem that caused nested loops to fail
  sometimes.

2020.7.0 (23 July 2020)
-----------------------

* Write the structure out at the end of each iteration so that it can
  be viewed in the dashboard.

0.9 (15 April 2020)
-------------------

* Support for plots in the dashboard.

0.7.0 (17 December 2019)
------------------------

* General clean-up of code and output.

0.6 (8 September 2019)
----------------------

* Cleaned up description.
* Internal: preparing for using PyUp to check dependencies.
  
0.2.0 (2019-07-29)
------------------

* First release on PyPI.

0.1.0 (2019-01-13)
------------------

* First version created in GitHub.
