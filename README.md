# Webpage automated test with URL
Automated test of webpage by giving URL and prompts of test cases.
## Workflow
Input: an URL and text of prompts (describe test cases).
1. Fetch HTML document of the webpage corresponding to the URL. Extract DOM structure from the HTML document.
2. Anyalze the testability of test cases from the prompt input.
3. Generate test codes.
4. Execute the test codes and check results. Return and display the results.
## Dependencies
Developed in Windows.
- python >= 3.12  
- python dependencies:  
    dotenv, pydantic, flask  
    pytest-playwright (used in fetching HTML document of the webpage)  
    langgraph, langchain (LLM agent)  
    langchain_openai (As an example LLM API here)  
- API key is needed for using the LLM. Please set the environment variable by written for example OPENAI_API_KEY="sk-..." in an .env file.
- In order to execute codes of automated testing, Selenium, Appium, or other automated testing framwork instructed in code generating should be setted in the environment. *(Maybe use Docker for replacement in the future.)*

- JavaScript dependencies:  
    Node.js (with NPM included)
    Use `npm install` command in a terminal opened in `frontend` folder to install the dependent packages.
    Packages mainly include: React, antd, etc.
    Your browser should support ES6, HTML5  

## Test of frontend and backend during development
### Frontend
Execute command: `path-to-the-project/frontend> npm start`
Running on `http://localhost:3000` by default.
### Backend
Execute command: `path-to-the-project/backend> python run.py`
Running on `http://localhost:5000` by default.