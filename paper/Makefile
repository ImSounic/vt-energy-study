main.pdf: main.tex refs.bib
	pdflatex -interaction=nonstopmode main
	bibtex main || true
	pdflatex -interaction=nonstopmode main
	pdflatex -interaction=nonstopmode main

clean:
	rm -f *.aux *.bbl *.blg *.log *.out main.pdf

.PHONY: clean
