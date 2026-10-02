# Prefer tectonic (fetches missing fonts/packages itself; used on the Mac);
# fall back to pdflatex+bibtex when tectonic is absent.
TECTONIC := $(shell command -v tectonic 2>/dev/null)

main.pdf: main.tex refs.bib sec-planning.tex sec-measurement.tex sec-threats.tex
ifneq ($(TECTONIC),)
	tectonic -X compile main.tex
else
	pdflatex -interaction=nonstopmode main
	bibtex main || true
	pdflatex -interaction=nonstopmode main
	pdflatex -interaction=nonstopmode main
endif

clean:
	rm -f *.aux *.bbl *.blg *.log *.out main.pdf

.PHONY: clean
