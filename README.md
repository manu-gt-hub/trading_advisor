# Cloud LLM Deployment (<trading advisor)>

Welcome to this example repository demonstrating how to deploy and run a Large Language Model (LLM) in the cloud! This project serves as a practical guide for setting up, deploying, and executing an LLM on cloud infrastructure, making it easy for developers and enthusiasts to learn and experiment.

## 🚀 Features

- Step-by-step deployment instructions
- Cloud setup for scalable LLM inference
- Example scripts to interact with the deployed model
- Basic monitoring and logging examples
- Easily adaptable to different cloud providers and models

## 🛠️ Getting Started

### (usage documented at the bottom)

### Prerequisites

- TBD

### Installation

1. Clone the repository  
   ```bash
   git clone https://github.com/manu-gt-hub/llm_deployment_test.git
   cd llm_deployment_test

### Useful commands

   ```bash
   # 1. Run all tests
   pytest

   # 2. Run tests with verbose output
   pytest -v

   # 3. Run tests showing logs at INFO level
   pytest --log-cli-level=INFO

   # 4. Run tests showing logs at DEBUG level
   pytest --log-cli-level=DEBUG

   # 5. Run a specific test file
   pytest tests/test_google_handler.py

   # 6. Run a specific test function inside a test file
   pytest tests/test_google_handler.py::test_load_data_real

   # 7. Run tests and stop after first failure
   pytest -x

   # 8. Run tests with coverage report (requires pytest-cov)
   pytest --cov=your_package_name

   # 9. Run the main Python script
   python main.py

   # 10. Run main script overriding environment variable (Linux/macOS)
   TRADING_ADVISOR_FOLDER_ID='your_folder_id' python main.py

   # Windows CMD
   set TRADING_ADVISOR_FOLDER_ID=your_folder_id
   python main.py

   # 11. Run pytest setting LOG_LEVEL environment variable
   LOG_LEVEL=DEBUG pytest

   # Windows CMD
   set LOG_LEVEL=DEBUG
   pytest

   # 12. Run tests and generate JUnit XML report (for CI)
   pytest --junitxml=reports/junit.xml
   ```

### Documentation

For detailed setup guides, architecture overview, and advanced usage, check out the /docs folder.

### ⚠️ Disclaimer

This repository is intended for educational and learning purposes only.
It is not optimized for production use, security, or scalability. Use responsibly and at your own risk.

### USAGE

Steps:

   - set variables for: Google drive space and files, finnhub, OpenAI, ALPHA vantage API key etc. 
   - add symbol to the ENV variable: SYMBOLS_INTEREST_LIST
   - add market related to symbol into the dictionary located on resources/symbols_markets.json
   - an analysis_file and buy_recommendation files would be created on the folder
   - (optional) force opinion for one LLM or another, or both as default if the opinion is equal
   - final decision is evaluated on: generals.generate_action_column()
   - to add/remove opinions, just use generals.add_opinion() over the final dataframe on main.py

### TEST

   - run: pytest in the terminal on the project root
   - run (example): pytest test/test_general.py -s
   - run E2E: python main.py --test

