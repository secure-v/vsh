# SHELL := /usr/bin/zsh

all: install

SHELLRC = bashrc


install:
	pip install pyDigitalWaveTools
	pip install cmd2
	pip install capstone
	chmod +x vsh.py
	mkdir -p ~/eda/vsh
	cp vsh.py ~/eda/vsh/vsh
	cp -r vcd_example ~/eda/vsh/
	sed -i '/eda\/vsh/d' ~/.$(SHELLRC)
	echo 'export PATH="$$HOME/eda/vsh/:$$PATH"' >> ~/.$(SHELLRC)
	bash -c "source ~/.$(SHELLRC)"
	@bash -c "source ~/.$(SHELLRC)"


install-zsh:
	pip install pyDigitalWaveTools
	pip install cmd2
	pip install capstone
	chmod +x vsh.py
	mkdir -p ~/eda/vsh
	cp vsh.py ~/eda/vsh/vsh
	cp -r vcd_example ~/eda/vsh/
	sed -i '/eda\/vsh/d' ~/.zshrc
	echo 'export PATH="$$HOME/eda/vsh/:$$PATH"' >> ~/.zshrc
	@zsh ~/.zshrc


uninstall:
	sed -i '/eda\/vsh/d' ~/.$(SHELLRC)
	sed -i '/eda\/vsh/d' ~/.zshrc
	rm -rf ~/eda/vsh

clean:
	rm -rf ~/eda/vsh

.PHONY: instal clean
