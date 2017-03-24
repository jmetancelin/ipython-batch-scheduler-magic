#!/bin/bash

cp AUTHORS.md README.md docs/source/.
mv docs html
make -C html html
mv html docs
