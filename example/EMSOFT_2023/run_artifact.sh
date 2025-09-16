#!usr/bin/bash
clear


PYTHONPATH=$PYTHONPATH:/home/jonas/Documents/git_repositories/python_sync_ethernet_analysis/pycpa

python3 case_study.py
python3 plot_data.py
