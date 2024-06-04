from time import time
import os
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["CUDA_VISIBLE_DEVICES"] = "0, 1, 2, 3"

from parent_agent import GPTagent
from textworld_adapter import TextWorldWrapper
from parent_graph import TripletGraph
from graphs.subgraph_strategy import SubgraphStrategy
from agents.direct_action_agent import DirectActionAgent
from agents.plan_in_json_agent import PlanInJsonAgent
from graphs.history import History, HistoryWithPlan
from graphs.extended_graphs import ExtendedGraphSubgraphStrategy, ExtendedGraphPagerankStrategy, \
    ExtendedGraphMixtralPagerankStrategy, ExtendedGraphDescriptionPagerankStrategy
from graphs.description_graphs import DescriptionGraphBeamSearchStrategy
from graphs.parent_without_emb import GraphWithoutEmbeddings
from graphs.dummy_graph import DummyGraph
from graphs.steps_in_triplets import StepsInTripletsGraph, LLaMAStepsInTripletsGraph
from prompts import *
from utils import *
from prompts_diff_agents import *
from agents.llama_agent import LLaMAagent


# There is configs of exp, changeable part of pipeline
# If you add some parameters, please, edit config
log_file = "exp_nav3_llama"
env_name = "benchmark/navigation3/navigation3_1.z8"
main_goal = "Find the treasure"
model = "gpt-4-0125-preview"
agent_instance = LLaMAagent
graph_instance = LLaMAStepsInTripletsGraph
history_instance = HistoryWithPlan
goal_freq = 10
threshold = 0.02
n_prev, majority_part = 3, 0.51

max_steps, n_attempts = 80, 1
n_neighbours = 4

system_prompt = system_prompt
config = {
    "log_file": log_file,
    "env_name": env_name,
    "main_goal": main_goal,
    "model": model,
    "goal_freq": goal_freq,
    "threshold": threshold,
    "system_prompt": system_prompt,
    "n_prev": n_prev,
    "majority_part": majority_part
}
# End of changeable part

log = Logger(log_file)

# Flexible init with only arguments class need
agent = agent_instance(**find_args(agent_instance, config))
config["pipeline"] = agent.pipeline
graph = graph_instance(**find_args(graph_instance, config))
history = history_instance(**find_args(history_instance, config))
env = TextWorldWrapper(env_name)
walkthrough = ["examine Task note", "take Key 1", "go west", "go south", "go east", "go east", "unlock White locker with Key 1", 
"open White locker", "take Key 2 from White locker", "examine Note 2", "go west", "go west", "unlock Red locker with Key 2", 
"open Red locker", "take Key 3 from Red locker", "take Note 3 from Red locker", "examine Note 3", "go east", "go east", 
"go north", "go north", "go west", "go east", "go east", "unlock Cyan locker with Key 3", "open Cyan locker", 
"take Golden key from Cyan locker", "go west", "go south", "go south", "go west", "go west", "go north", 
"go east", "unclock Golden locker with Golden key", "unlock Golden locker with Golden key", "open Golden locker", 
"take treasure from Golden locker"]

explore_all_rooms = ["west", "north", "south", "south", "south", "north", "east", "east", "south", "north", "north", "north", 
                     "west", "east", "east"]

agent_if_exp = LLaMAagent(system_prompt= if_exp_prompt, pipeline = agent.pipeline) 
agent_plan = LLaMAagent(system_prompt=system_plan_agent, pipeline = agent.pipeline)
agent_action = LLaMAagent(system_prompt=system_action_agent_sub_expl, pipeline = agent.pipeline)

locations = set()
# observation, info = env.reset()
action = "start"
plan0 = "Explore all locations"
subgraph = "Nothing there"
description = "Nothing there"
# previous_location = env.curr_location.lower()
# for exp_act in explore_all_rooms:
#     start = time()
#     observation = observation.split("$$$")[-1]
#     inventory = env.get_inventory()
#     observation += f"\nInventory: {inventory}"
#     observation += f"\nAction that led to this: {action}"
#     log("Observation: " + observation)
    
#     locations.add(env.curr_location.lower())    
#     subgraph, description = graph.update(observation, plan0, subgraph, description, locations, env.curr_location.lower(), previous_location, action, 0, log)
#     previous_location = env.curr_location.lower()

#     observation, reward, done, info = env.step(exp_act)
#     action = exp_act
# os.makedirs("Visit_graph", exist_ok=True)
# graph.save("Visit_graph")
    

observations, hist = [], []
tried_action = {}
total_amount, total_time = 0, 0

for i in range(n_attempts):
    log("Attempt: " + str(i + 1))
    log("=" * 70)
    observation, info = env.reset()
    agent.reset()
    action = "start"
    goal = "Start game"
    plan0 = f'''{{
  "main_goal": {main_goal},
  "plan_steps": [
    {{
      "sub_goal_1": "Start the game",
      "reason": "You should start the game"
    }},
  ],
}}'''
    subgraph = []
    description = "Nothing there"
    previous_location = env.curr_location.lower()
    attempt_amount, attempt_time = 0, 0
    done = False
    action_history = []
    for step in range(max_steps):
    # for step, new_action in enumerate(walkthrough[:25]):
        start = time()
        log("Step: " + str(step + 1))
        observation = observation.split("$$$")[-1]
        if step == 0:
            observation += f""" \n Your task is to get a treasure. Treasure is hidden in the golden locker. You need a golden key to unlock it. The key is hidden in one of the other lockers located in the environment. All lockers are locked and require a specific key to unlock. The key 1 you found in room A unlocks white locker. Read the notes that you find, they will guide you further."""
        observation = "Step: " + str(step + 1) + "\n" + observation
        inventory = env.get_inventory()
        observation += f"\nInventory: {inventory}"
        observation += f"\nAction that led to this: {action}"
        # if env.curr_location.lower() in tried_action:
        #     observation += f"\nActions that you tried here before: {tried_action[env.curr_location.lower()]}"
        # observation += f"\nActions that you made since game started: {action_history}"
        # observation += f"\nGoal that led to this: {goal}"
        log("Observation: " + observation)
        
        locations.add(env.curr_location.lower())
        
        observed_items = agent.bigraph_processing1(observation, plan0)
        items = [list(item.keys())[0] for item in observed_items]
        log("Crucial items: " + str(items))
        items_lower = [element.lower() for element in items]
        # associated_subgraph = graph.update(observation=observation, observations=observations, locations=list(locations), curr_location=env.curr_location.lower(), previous_location=previous_location, action=action, log=log, items=items, goal="")
        subgraph = graph.update(observation, observations, plan=plan0, locations=list(locations), curr_location=env.curr_location.lower(), previous_location=previous_location, action=action, log=log, step = step + 1, items = items)
        
        log("Length of subgraph: " + str(len(subgraph)))
        log("Associated triplets: " + str(subgraph))
        # while True:
        #     triplet = input("Enter triplet: ")
        #     if triplet == "end":
        #         break
        #     subgraph.append(f"Step {step + 1}: {triplet}")
        
        # if if_explore == True:
        valid_actions = env.get_valid_actions() + [f"go to {loc}" for loc in locations]
        tried_now = {act[0] for act in tried_action[env.curr_location.lower()]}\
            if env.curr_location.lower() in tried_action else {}
        not_yet_tried = list({act for act in valid_actions if act not in tried_now})
        log("Actions that isn't tried: " + str(not_yet_tried))
        prompt = f'''\n1. Main goal: {main_goal}
    \n2. History of {n_prev} last observations and actions: {observations} 
    \n3. Your current observation: {observation}
    \n4. Information from the memory module that can be relevant to current situation: {subgraph}
    \n5. Your current plan: {plan0}
    \n6. History of your actions: {action_history}
    Remember that you should not repeat actions when you explore.
    \n7. Actions that you haven't tried at current location: {not_yet_tried}
    This actions must have highest priority when you explore.
    
    Remember that you should not visit locations and states that you visited before when you are exploring.
    '''
        plan0, cost_plan = agent_plan.generate(prompt, jsn=True, t=0.2)
        log("Plan0: " + plan0)
        plan_json = json.loads(plan0)
       
        sub_goal_1 = plan_json["plan_steps"][0]["sub_goal_1"]
        reason1 = plan_json["plan_steps"][0]["reason"]
        
        # if_explore, cost = agent_if_exp.generate(prompt=f"Plan: \n{plan0}", t=0.2)
        # if_explore = if_explore == "True"
        # log('if_exp: ' + str(if_explore))
    #     else:
    #         prompt = f'''\n1.Main goal: {main_goal}
    # \n2. History of {n_prev} last observations and actions: {observations} 
    # \n3. Your current observation: {observation}
    # \n4. {inventory}
    # \n5. Information from the memory module that can be relevant to current situation: {subgraph}
    # \n6. Your current plan: {plan0}
    # '''


        #Generate action
        # acts_with_cons = graph.get_conseq(tried_action[env.curr_location.lower()])\
        #     if env.curr_location.lower() in tried_action else []
        # log("Actions with consequences: " + str(acts_with_cons))
        
        prompt = f'''\n1. Main goal: {main_goal}
\n2. History of {n_prev} last observations and actions: {observations} 
\n3. Your current observation: {observation}
\n4. Information from the memory module that can be relevant to current situation:  {subgraph}
\n5. Your current plan: {plan0}
\n6. History of your actions: {action_history}
Remember that you should not repeat actions when you explore.
\n7. Actions that you haven't tried at current location: {not_yet_tried}
This actions must have highest priority when you explore. 

Possible actions in current situation (you should choose three actions from this list and estimate their probabilities): {valid_actions}'''          
        action0, cost_action = agent_action.generate(prompt, jsn=True, t=0.2)
        action_json = json.loads(action0)
        log("Action: " + action0)
        
        for key in action_json:
            action_json[key] = float(action_json[key])
        
        # if env.curr_location.lower() in tried_action and if_explore:
        #     loc_act = tried_action[env.curr_location.lower()]
        #     scores = {val_act: 1 / loc_act[val_act] if val_act in loc_act else 1 / 0.3 for val_act in valid_actions}
        #     sum_scores = sum(list(scores.values()))
        #     alpha = 2 / sum_scores
        #     for val_act in scores:
        #         scores[val_act] /= sum_scores
        #         if val_act in action_json:
        #             scores[val_act] += action_json[val_act] * alpha
        #     sum_scores = sum(list(scores.values()))
        #     for val_act in scores:
        #         scores[val_act] /= sum_scores      
        #     action_json = scores
            
        action = sorted([(score, act) for act, score in action_json.items()])[-1][1]
        log("Actions scores: " + str(sorted([(score, act) for act, score in action_json.items()], reverse = True)))
        
        observations.append(observation)
        observations = observations[-n_prev:]
        previous_location = env.curr_location.lower()
        
        is_nav = "go to" in action
        if is_nav:
            destination = action.split('go to ')[1]
            path = graph.find_path(env.curr_location, destination, locations)
            print("path", path)
            if not isinstance(path, list):
                observation = path
            else:
                log("\n\nNAVIGATION\n\n")
                for hidden_step, hidden_action in enumerate(path):
                    observation, reward, done, info = env.step(hidden_action)
                    if done:
                        break
                    log("Navigation step: " + str(hidden_step + 1))
                    log("Observation: " + observation + "\n\n")
        else:
            observation, reward, done, info = env.step(action)
            
        act_for_hist = action.lower()
        if is_nav or "north" in act_for_hist or "south" in act_for_hist or "east" in act_for_hist or "west" in act_for_hist:
            act_for_hist += f" (found yourself at {env.curr_location})"
        action_history.append(act_for_hist)
        
        if previous_location not in tried_action:
            tried_action[previous_location] = [(action, step + 1)]
        else:
            tried_action[previous_location].append((action, step + 1))
        
        step_amount = agent.total_amount + graph.total_amount + agent_plan.total_amount + agent_action.total_amount + agent_if_exp.total_amount - total_amount
        attempt_amount += step_amount
        total_amount += step_amount
        log(f"\nTotal amount: {round(total_amount, 2)}$, attempt amount: {round(attempt_amount, 2)}$, step amount: {round(step_amount, 2)}$")
        
        step_time = time() - start
        attempt_time += step_time
        total_time += step_time
        log(f"Total time: {round(total_time, 2)} sec, attempt time: {round(attempt_time, 2)} sec, step time: {round(step_time, 2)} sec")
        log("=" * 70)
        
        graph.save(log_file)
        history.save(log_file)