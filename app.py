import json
import os
import urllib.request
from datetime import datetime
import requests

def make_request(endpoint, circle_token):
    header = {
        'Circle-Token': circle_token,
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    req = urllib.request.Request(endpoint, headers=header)
    return json.loads(urllib.request.urlopen(req).read())

def pipelines_res(project_slug, circle_token):
    pipelines_endpoint = f'https://circleci.com/api/v2/project/{project_slug}/pipeline'
    pipelines = make_request(pipelines_endpoint, circle_token)
    return pipelines['items']


def func_k_actor_v_pipelines(pipelines):
    res = {}
    for pipeline in pipelines:
        actor = pipeline['trigger']['actor']['login']
        if actor not in res:
            res[actor] = []
        pipeline_id = pipeline["id"]
        res[actor].append(pipeline_id)
    return res


def func_k_actor_v_created_arr(pipelines):
    res = {}
    for pipeline in pipelines:
        actor = pipeline['trigger']['actor']['login']
        if actor not in res:
            res[actor] = []
        created_at = datetime.fromisoformat(pipeline['created_at'][:-1])
        res[actor].append(created_at)
    return res


def func_k_actor_v_pipeline_created_limit(k_actor_v_created_arr_dict, last_time, threshold_seconds):
    # latest_time = datetime.fromisoformat(last_time)
    res = {}
    for actor, times in k_actor_v_created_arr_dict.items():
        res[actor] = [(last_time - time).seconds for time in times if (last_time - time).seconds < threshold_seconds]
    return res


def func_errant_workflows(pipelines, circle_token):
    res = []
    for pipeline_id in pipelines:
        pipeline_endpoint = f'https://circleci.com/api/v2/pipeline/{pipeline_id}/workflow'
        pipeline = make_request(pipeline_endpoint, circle_token)
        res.extend([workflow['id'] for workflow in pipeline['items']])
    return res


def flatten(l):
    return [item for sublist in l for item in sublist]

def main():
    vcs = 'gh'

    org_env_var = os.getenv('SLACK_MONITOR_CIRCLE_PROJECT_USERNAME_ENVVAR')
    repo_env_var = os.getenv('SLACK_MONITOR_CIRCLE_PROJECT_REPONAME_ENVVAR')
    circle_token_env_var = os.getenv('SLACK_MONITOR_CIRCLE_TOKEN_ENVVAR')
    slack_app_url_env_var = os.getenv('SLACK_MONITOR_SLACK_APP_URL_ENVVAR')

    # circle project vars
    org = os.getenv(org_env_var)
    repo = os.getenv(repo_env_var)

    # secrets
    circle_token = os.getenv(circle_token_env_var)
    slack_app_url = os.getenv(slack_app_url_env_var)

    # from parameters
    threshold_seconds = int(
        os.getenv('SLACK_MONITOR_PARAM_THRESHOLD_SECONDS')
    )
    print('threshold seconds: ', threshold_seconds)
    # max builds triggered by a single user within threshold_seconds of the current time
    alert_threshold_user = int(
        os.getenv('SLACK_MONITOR_PARAM_THRESHOLD_MAX_BUILDS_PER_USER')
    )
    print('alert_threshold_user ', alert_threshold_user)
    # max within a minute of the latest build that triggers an alert, must be < 30
    alert_threshold_build = int(
        os.getenv('SLACK_MONITOR_PARAM_THRESHOLD_MAX_BUILDS')
    )
    print('alert_threshold_build ', alert_threshold_build)

    user_alert = False
    build_alert = False

    project_slug = f'{vcs}/{org}/{repo}'
    pipelines = pipelines_res(project_slug, circle_token)
    current_time = datetime.now()
    current_time_str = datetime.now().isoformat()
    oldest_pipeline_date = pipelines[-1]["created_at"][:-1]

    k_actor_v_created_arr = func_k_actor_v_created_arr(pipelines)
    print(k_actor_v_created_arr)
    k_actor_v_pipelines = func_k_actor_v_pipelines(pipelines)
    k_actor_v_pipeline_created_limit = func_k_actor_v_pipeline_created_limit(
        k_actor_v_created_arr,
        current_time,
        threshold_seconds
    )

    print(k_actor_v_pipeline_created_limit)
    
    for actor, pipeline_ids in k_actor_v_pipeline_created_limit.items():
        if len(pipeline_ids) > alert_threshold_user:
            user_alert = True
            pipelines_by_errant_actor = k_actor_v_pipelines[actor]
            alert_text = f'*{actor}* has triggered {len(pipeline_ids)} pipelines in the past {threshold_seconds} seconds\n ' \
                         f'(since {current_time}).\n' \
                         f'Any running workflows triggered since {oldest_pipeline_date} will be cancelled.'

            user_alert_msg = {
                     "blocks": [
                         {
                             "type": "section",
                             "text": {
                                 "type": "mrkdwn",
                                 "text": '*USER ALERT*'
                             }
                         },
                         {
                             "type": "section",
                             "text": {
                                 "type": "mrkdwn",
                                 "text": alert_text
                             }
                         },
                     ]
            }
            requests.post(slack_app_url, json=user_alert_msg)

            # identify and cancel workflows by this user
            errant_workflows = func_errant_workflows(pipelines_by_errant_actor, circle_token)
            for workflow_id in errant_workflows:
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Circle-Token': circle_token
                }
                r = requests.post(f'https://circleci.com/api/v2/workflow/{workflow_id}/cancel', headers=headers)
                print(r.content)

    pipelines_run_in_last_minute = []
    for pipeline in pipelines:
        created_at_str = pipeline['created_at'][:-1]
        created_at = datetime.fromisoformat(created_at_str)
        if (current_time - created_at).seconds < threshold_seconds:
            pipelines_run_in_last_minute.append(created_at_str)

    if len(pipelines_run_in_last_minute) > alert_threshold_build:
        build_alert = True
        alert_text = f"There have been *{len(pipelines_run_in_last_minute)} pipelines* triggered between " \
                     f"{pipelines_run_in_last_minute[-1]} and {current_time_str}."
        build_alert_msg = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": '*BUILD ALERT*'
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": alert_text
                    }
                },
            ]
        }
        requests.post(slack_app_url, json=build_alert_msg)
    print({
            "user_alert": user_alert,
            "build_alert": build_alert
    })

main()
