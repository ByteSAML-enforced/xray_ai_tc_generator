import requests
from requests.auth import HTTPBasicAuth
import json
import openai
import argparse
from test_case_parser import filter_test_cases
# from generate_json import generate_with_openai

OPENAI_TOKEN_FILE = 'openai_token.txt'  # https://help.openai.com/en/articles/4936850-where-do-i-find-my-secret-api-key
AI_MODEL        = "gpt-4" # "gpt-3.5-turbo"

# Jira Cloud configuration
JIRA_TOKEN_FILE = 'jira_token.txt' # https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/

# Jira Cloud API endpoint for creating issues (test cases)
XRAY_URL        = "https://xray.cloud.getxray.app/api/v2/import/test/bulk"
XRAY_AUTH_JSON  = 'xray_auth.json'  # File containing your XRAY API token https://community.atlassian.com/t5/Jira-Software-questions/Where-to-create-Xray-api-key/qaq-p/1923024

# Fetch Requirement Issue data
def get_issue_data(issue_key, BASE_URL, USERNAME):
    with open(JIRA_TOKEN_FILE, 'r') as file:
        JIRA_TOKEN = file.readline().strip()
    url = f"{BASE_URL}/issue/{issue_key}"

    headers = {
        'Accept': 'application/json',
    }
    
    response = requests.get(
        url,
        headers=headers,
        auth=HTTPBasicAuth(USERNAME, JIRA_TOKEN)
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch issue data. Status code: {response.status_code}")
        print(response.text)
        return None
    
# Define Test Case Issue
def delete_test_case(issue_key, BASE_URL, USERNAME):
    with open(JIRA_TOKEN_FILE, 'r') as file:
        JIRA_TOKEN = file.readline().strip()
    url = f"{BASE_URL}/issue/{issue_key}"

    headers = {
        'Accept': 'application/json',
    }
    
    response = requests.delete(
        url,
        headers=headers,
        auth=HTTPBasicAuth(USERNAME, JIRA_TOKEN)
    )
    
    if response.status_code == 204:
        print("Test Case deleted successfully!")
    else:
        print(f"Failed to delete Test Case. Status code: {response.status_code}")
        print(response.text)
        return None
 
def generate_with_openai(prompt, tc_amount, skip_checks, debug):
    with open(OPENAI_TOKEN_FILE, 'r') as file:
        openai.api_key = file.readline().strip()

    # Create Prompt for OpenAI
    system_prompt = "Define " + str(tc_amount) + " Test Cases for the provided requirement specification. it. Note: Response must be in plain json format.\n\nJson format to use:\n\n[\n    {\n        \"testtype\": \"Manual\",\n        \"fields\": {\n            \"summary\": \"Test Case 1: Minimum Speed Test\",\n            \"description\": \"Objective: To verify that...\\n Preconditions: ...\"\n        },\n        \"steps\": [\n            {\n                \"action\": \"Begin a data fetch to ...\",\n                \"data\": \"\",\n                \"result\": \"Data fetch operation must be completed...\"\n            },\n        ]\n    }\n]"
    response = openai.chat.completions.create(
      model= AI_MODEL,
      messages=[
          {
          "role": "system",
          "content": system_prompt
          },
          {
          "role": "user",
          "content": prompt
          }
      ],
      temperature=0.1,
      max_tokens=2048,
      top_p=1,
      frequency_penalty=0,
      presence_penalty=0
      )
    # json_result = response['choices'][0]['message']['content'] # This is for v1 of the openai package: pypi.org/project/openai
    json_result = response.choices[0].message.content
    if debug: 
        print(json_result)
        print("Generation Done. Tokens used: " + str(response['usage']['total_tokens']))

    # Ask user which test cases to keep and filter
    if skip_checks == False:
        filtered_json_output = filter_test_cases(json_result)
    else:
        filtered_json_output = json_result

    with open('output_tc.json', 'w') as file:
        # json.dump(response['choices'][0]['message']['content'], file)
        json.dump(filtered_json_output, file)
    
    return

def import_test_cases_to_xray(JIRA_PARENT_ISSUE, debug):

    # get XRAY token
    url = "https://xray.cloud.getxray.app/api/v2/authenticate"
    headers = {
        "Content-Type": "application/json"
    }
    with open(XRAY_AUTH_JSON, "r") as file:
        data = file.read()
    response = requests.post(url, headers=headers, data=data)
    # Removing double quotes from the response
    API_TOKEN = response.text.replace('"', '')

    AUTH = (API_TOKEN)

    # Open the file for reading
    with open('output_tc.json', 'r') as file:
        content_string = file.read()

    data = json.loads(json.loads(content_string))
    if debug: print(data)

    if not isinstance(data, list):
        raise ValueError("The JSON structure is not as expected.")

    for testcase in data:
        testcase['fields']['project'] = json.loads('{ "key": "' + JIRA_PARENT_ISSUE.split("-")[0] + '" }') # "project": { "key": "TSX" } 
        testcase['update'] = json.loads('{ "issuelinks": [ { "add": { "type": { "name": "Test" }, "outwardIssue": { "key": "' + JIRA_PARENT_ISSUE + '" } } } ] }')   
        
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'Bearer ' + AUTH
    }

    if debug: print(json.dumps(data))

    response = requests.post(XRAY_URL, headers=headers, data=json.dumps(data))

    # Check for successful request
    if response.status_code == 200 or response.status_code == 201:
        print("Test cases imported successfully!")
        print(response.json())
    else:
        print(f"Failed to import test cases. Status code: {response.status_code}")
        print(response.text)
        print(data)

        
def main(req, username, baseurl, tc_amount, skip_checks, del_tc, debug):
    url = baseurl + '/rest/api/2'
    issue_data = get_issue_data(req, url, username)
    
    if issue_data:
        summ = "Requirement summary: " + issue_data['fields']['summary']
        # Check if issue type is requirement i.e. not type of 'Test', 'Test Set' or 'Test Plan'
        issueType = str(issue_data['fields']['issuetype']['name'])
        print("Issue type: " + issueType)
        if issueType == "Test" or issueType == "Test Set" or issueType == "Test Plan":
            print("Issue type is not a requirement. You cannot create linked Test Case for a Test item. Exiting.")
            exit()
        # Check if issue has description    
        if issue_data['fields']['description']:
            desc = "Requirement description: " + issue_data['fields']['description']
        else: 
            desc = " "
            print("No Description using summary only!")     
        req_data = summ + "\n" + desc
        print("Req data found:" + req + "\n" + req_data, flush=True)        
    else:
        print("No love. Issue not found for id: " + req)
        exit()

    # Check does issue have linked Test Cases
    if del_tc and issue_data['fields']['issuelinks']:
        # Loop through all linked issues
        for issue in issue_data['fields']['issuelinks']:
            # Check if linked issue is of type 'Test'
            if issue['type']['name'] == "Test":
                delete_test_case(issue['inwardIssue']['key'], url, username)
                print("Deleted linked Test Case: " + issue['inwardIssue']['key'], flush=True)
  
    if skip_checks:
        print("Skipping checks.")
        generate_with_openai(req_data, tc_amount, skip_checks, debug)
        import_test_cases_to_xray(req, debug)
    else:
        if input("Generate Test Cases: [y]/n?") != "n":
            generate_with_openai(req_data, tc_amount, skip_checks, debug)
            if input("Import Test Cases to XRAY: [y]/n?") != "n":
                import_test_cases_to_xray(req, debug)
        else:
            print("No Test Cases generated. Exiting.")
            exit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create XRAY Test Cases into Jira requirement using AI.")
    parser.add_argument('--req', required=True, help='Requirement Issue ID.')
    parser.add_argument('--username', required=True, help='Jira user name for login.')
    parser.add_argument('--url', required=True, help='Jira Cloud URL.')
    parser.add_argument('--tc_amount', type=int, default=1, help='Amount of Test Cases to generate. Default is 1.')
    parser.add_argument('--debug', type=bool, default=False, help='Debug flag. Default is False.')
    parser.add_argument('--skip_checks', type=bool, default=False, help='Skip confirmation questions. Default is False.')
    parser.add_argument('--del_tc', type=bool, default=False, help='Delete existing linked Test Cases. Default is False.')

    args = parser.parse_args()

    main(args.req, args.username, args.url, args.tc_amount, args.skip_checks, args.del_tc, args.debug)


