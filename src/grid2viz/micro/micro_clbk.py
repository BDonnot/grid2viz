import datetime as dt

import pandas as pd
import plotly.graph_objects as go
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import numpy as np

from src.app import app
from src.grid2kpi.episode_analytics import observation_model, EpisodeTrace
from src.grid2kpi.manager import episode, make_episode, base_dir, indx, prod_types, make_network, get_network_graph
from src.grid2viz.utils.graph_utils import relayout_callback, get_axis_relayout


@app.callback(
    Output("relayoutStoreMicro", "data"),
    [Input("env_charts_ts", "relayoutData"),
     Input("usage_rate_ts", "relayoutData"),
     Input("overflow_ts", "relayoutData"),
     Input("cum_instant_reward_ts", "relayoutData"),
     Input("actions_ts", "relayoutData"),
     Input("voltage_flow_graph", "relayoutData")],
    [State("relayoutStoreMicro", "data")]
)
def relayout_store_overview(*args):
    return relayout_callback(*args)


@app.callback(
    Output("window", "data"),
    [Input("enlarge_left", "n_clicks"),
     Input("enlarge_right", "n_clicks"),
     Input("user_timestamps", "value")],
    [State('agent_study', 'data')]
)
def compute_window(n_clicks_left, n_clicks_right, user_selected_timestamp,
                   study_agent):
    if user_selected_timestamp is None:
        raise PreventUpdate
    if n_clicks_left is None:
        n_clicks_left = 0
    if n_clicks_right is None:
        n_clicks_right = 0
    new_episode = make_episode(base_dir, study_agent, indx)
    center_indx = new_episode['data'].timestamps.index(
        dt.datetime.strptime(user_selected_timestamp, '%Y-%m-%d %H:%M')
    )
    timestamp_range = new_episode['data'].timestamps[
                      max([0, (center_indx - 10 - 5 * n_clicks_left)]):(center_indx + 10 + 5 * n_clicks_right)
                      ]
    xmin = timestamp_range[0].strftime("%Y-%m-%dT%H:%M:%S")
    xmax = timestamp_range[-1].strftime("%Y-%m-%dT%H:%M:%S")

    return (xmin, xmax)


# indicator line
@app.callback(
    Output("cum_instant_reward_ts", "figure"),
    [Input("relayoutStoreMicro", "data"),
     Input("window", "data"),
     Input("user_timestamps", "value")],
    [State("cum_instant_reward_ts", "figure"),
     State("agent_study", "data"),
     State("agent_ref", "data")]
)
def load_reward_ts(relayout_data_store, window, selected_timestamp, figure, study_agent, agent_ref):
    if selected_timestamp is None:
        raise PreventUpdate

    if relayout_data_store is not None and relayout_data_store["relayout_data"]:
        relayout_data = relayout_data_store["relayout_data"]
        layout = figure["layout"]
        new_axis_layout = get_axis_relayout(figure, relayout_data)
        if new_axis_layout is not None:
            layout.update(new_axis_layout)
            return figure

    new_episode = make_episode(base_dir, study_agent, indx)
    ref_episode = make_episode(base_dir, agent_ref, indx)
    actions_ts = new_episode['data'].action_data.set_index("timestamp")[[
        'action_line', 'action_subs'
    ]].sum(axis=1).to_frame(name="Nb Actions")
    df = observation_model.get_df_computed_reward(new_episode['data'])
    action_events_df = pd.DataFrame(
        index=df["timestep"], data=np.nan, columns=["action_events"])
    action_events_df.loc[(actions_ts["Nb Actions"] > 0).values, "action_events"] = \
        df.loc[(actions_ts["Nb Actions"] > 0).values, "rewards"].values
    action_trace = go.Scatter(
        x=action_events_df.index, y=action_events_df["action_events"], name="Actions",
        mode='markers', marker_color='#FFEB3B',
        marker={"symbol": "hexagon", "size": 10}
    )
    ref_episode_reward_trace = ref_episode['reward_trace']
    studied_agent_reward_trace = make_episode(base_dir, study_agent, indx)['reward_trace']

    figure['data'] = [*ref_episode_reward_trace, *studied_agent_reward_trace,
                      action_trace]
    figure['layout'] = {**figure['layout'],
                        'yaxis2': {'side': 'right', 'anchor': 'x', 'overlaying': 'y'}, }

    if window is not None:
        figure["layout"].update(
            xaxis=dict(range=window, autorange=False)
        )

    return figure


@app.callback(
    Output("actions_ts", "figure"),
    [Input('relayoutStoreMicro', 'data'),
     Input("window", "data")],
    [State("actions_ts", "figure"),
     State("user_timestamps", "value"),
     State('agent_study', 'data'),
     State('agent_ref', 'data')]
)
def load_actions_ts(relayout_data_store, window, figure, selected_timestamp, study_agent, agent_ref):
    if selected_timestamp is None:
        raise PreventUpdate

    if relayout_data_store is not None and relayout_data_store["relayout_data"]:
        relayout_data = relayout_data_store["relayout_data"]
        layout = figure["layout"]
        new_axis_layout = get_axis_relayout(figure, relayout_data)
        if new_axis_layout is not None:
            layout.update(new_axis_layout)
            return figure

    new_episode = make_episode(base_dir, study_agent, indx)['data']
    actions_ts = new_episode.action_data.set_index("timestamp")[[
        'action_line', 'action_subs'
    ]].sum(axis=1).to_frame(name="Nb Actions")
    ref_episode = make_episode(base_dir, agent_ref, indx)['data']
    ref_agent_actions_ts = ref_episode.action_data.set_index("timestamp")[[
        'action_line', 'action_subs'
    ]].sum(axis=1).to_frame(name="Nb Actions")
    figure["data"] = [
        go.Scatter(x=new_episode.action_data.timestamp,
                   y=actions_ts["Nb Actions"], name=study_agent,
                   text=action_tooltip(new_episode.actions)),
        go.Scatter(x=new_episode.action_data.timestamp,
                   y=ref_agent_actions_ts["Nb Actions"], name=agent_ref,
                   text=action_tooltip(ref_episode.actions)),

        go.Scatter(x=new_episode.action_data.timestamp,
                   y=new_episode.action_data["distance"], name=study_agent + " distance", yaxis='y2'),
        go.Scatter(x=new_episode.action_data.timestamp,
                   y=ref_episode.action_data["distance"], name=agent_ref + " distance", yaxis='y2'),
    ]
    figure['layout'] = {**figure['layout'],
                        'yaxis2': {'side': 'right', 'anchor': 'x', 'overlaying': 'y'}, }

    if window is not None:
        figure["layout"].update(
            xaxis=dict(range=window, autorange=False)
        )

    return figure


def action_tooltip(episode_actions):
    tooltip = []
    actions_impact = [action.impact_on_objects() for action in episode_actions]

    for action in actions_impact:
        impact_detail = []
        if action['has_impact']:
            injection = action['injection']
            force_line = action['force_line']
            switch_line = action['switch_line']
            topology = action['topology']

            if injection['changed']:
                for detail in injection['impacted']:
                    impact_detail.append(" injection set {} to {} <br>"
                                         .format(detail['set'], detail['to']))

            if force_line['changed']:
                reconnections = force_line['reconnections']
                disconnections = force_line['disconnections']

                if reconnections['count'] > 0:
                    impact_detail.append(" force reconnection of {} powerlines ({}) <br>"
                                         .format(reconnections['count'], reconnections['powerlines']))

                if disconnections['count'] > 0:
                    impact_detail.append(" force disconnection of {} powerlines ({}) <br>"
                                         .format(disconnections['count'], disconnections['powerlines']))

            if switch_line['changed']:
                impact_detail.append(" switch status of {} powerlines ({}) <br>"
                                     .format(switch_line['count'], switch_line['powerlines']))

            if topology['changed']:
                bus_switch = topology['bus_switch']
                assigned_bus = topology['assigned_bus']
                disconnected_bus = topology['disconnect_bus']

                if len(bus_switch) > 0:
                    for switch in bus_switch:
                        impact_detail.append(" switch bus of {} {} on substation {} <br>"
                                             .format(switch['object_type'], switch['object_id'],
                                                     switch['substation']))
                if len(assigned_bus) > 0:
                    for assignment in assigned_bus:
                        impact_detail.append(" assign bus {} to {} {} on substation {} <br>"
                                             .format(assignment['bus'], assignment['object_type'],
                                                     assignment['object_id'], assignment['substation']))
                if len(disconnected_bus) > 0:
                    for disconnection in disconnected_bus:
                        impact_detail.append(" disconnect bus {} {} on substation {} <br>"
                                             .format(disconnection['object_type'], disconnection['object_id'],
                                                     disconnection['substation']))
            tooltip.append(''.join(impact_detail))
        else:
            tooltip.append('Do nothing')

    return tooltip


# flux line callback
@app.callback(
    [Output('line_side_choices', 'options'),
     Output('line_side_choices', 'value')],
    [Input('voltage_flow_selector', 'value')],
    [State('agent_study', 'data')]
)
def load_voltage_flow_line_choice(value, study_agent):
    option = []
    new_episode = make_episode(base_dir, study_agent, indx)

    for name in new_episode['data'].line_names:
        if value == 'voltage':
            option.append({
                'label': 'ex_' + name,
                'value': 'ex_' + name
            })
            option.append({
                'label': 'or_' + name,
                'value': 'or_' + name
            })
        if value == 'flow':
            option.append({
                'label': 'ex_active_' + name,
                'value': 'ex_active_' + name
            })
            option.append({
                'label': 'ex_reactive_' + name,
                'value': 'ex_reactive_' + name
            })
            option.append({
                'label': 'ex_current_' + name,
                'value': 'ex_current_' + name
            })
            option.append({
                'label': 'or_active_' + name,
                'value': 'or_active_' + name
            })
            option.append({
                'label': 'or_reactive_' + name,
                'value': 'or_reactive_' + name
            })
            option.append({
                'label': 'or_current_' + name,
                'value': 'or_current_' + name
            })

    return option, [option[0]['value']]


@app.callback(
    Output('voltage_flow_graph', 'figure'),
    [Input('line_side_choices', 'value'),
     Input('voltage_flow_selector', 'value'),
     Input('relayoutStoreMicro', 'data'),
     Input("window", "data")],
    [State('voltage_flow_graph', 'figure'),
     State('agent_study', 'data')]
)
def load_flow_voltage_graph(selected_lines, select_cat, relayout_data_store, window, figure, study_agent):
    if relayout_data_store is not None and relayout_data_store["relayout_data"]:
        relayout_data = relayout_data_store["relayout_data"]
        layout = figure["layout"]
        new_axis_layout = get_axis_relayout(figure, relayout_data)
        if new_axis_layout is not None:
            layout.update(new_axis_layout)
            return figure
    new_episode = make_episode(base_dir, study_agent, indx)['data']
    if selected_lines is not None:
        if select_cat == 'voltage':
            figure['data'] = load_voltage_for_lines(selected_lines, new_episode)
        if select_cat == 'flow':
            figure['data'] = load_flow_for_lines(selected_lines, new_episode)

    if window is not None:
        figure["layout"].update(
            xaxis=dict(range=window, autorange=False)
        )

    return figure


def load_voltage_for_lines(lines, new_episode):
    voltage = new_episode.flow_and_voltage_line
    traces = []

    for value in lines:
        # the first 2 characters are the side of line ('ex' or 'or')
        line_side = str(value)[:2]
        line_name = str(value)
        if line_side == 'ex':
            traces.append(go.Scatter(
                x=new_episode.timestamps,
                # remove the first 3 char to get the line name and round to 3 dec
                y=voltage['ex']['voltage'][line_name[3:]],
                name=line_name)
            )
        if line_side == 'or':
            traces.append(go.Scatter(
                x=new_episode.timestamps,
                y=voltage['or']['voltage'][line_name[3:]],
                name=line_name)
            )
    return traces


def load_flow_for_lines(lines, new_episode):
    flow = new_episode.flow_and_voltage_line
    traces = []

    for value in lines:
        line_side = str(value)[:2]  # the first 2 characters are the side of line ('ex' or 'or')
        flow_type = str(value)[3:].split('_', 1)[0]  # the type is the 1st part of the string: 'type_name'
        line_name = str(value)[3:].split('_', 1)[1]  # the name is the 2nd part of the string: 'type_name'
        x = new_episode.timestamps
        if line_side == 'ex':
            traces.append(go.Scatter(
                x=x,
                y=flow['ex'][flow_type][line_name],
                name=value)
            )
        elif line_side == 'or':
            traces.append(go.Scatter(
                x=x,
                y=flow['or'][flow_type][line_name],
                name=value)
            )
    return traces


# context line callback
@app.callback(
    [Output("asset_selector", "options"),
     Output("asset_selector", "value")],
    [Input("environment_choices_buttons", "value")],
    [State("agent_study", "data")]
)
def update_ts_graph_avail_assets(kind, study_agent):
    new_episode = make_episode(base_dir, study_agent, indx)['data']
    if kind in ["Hazards", "Maintenances"]:
        options, value = [{'label': line_name, 'value': line_name}
                          for line_name in [*new_episode.line_names, 'total']], new_episode.line_names[0]
    elif kind == 'Production':
        options = [{'label': prod_name,
                    'value': prod_name}
                   for prod_name in [*new_episode.prod_names, *list(set(prod_types.values())), 'total']]
        value = new_episode.prod_names[0]
    else:
        options = [{'label': load_name,
                    'value': load_name}
                   for load_name in [*new_episode.load_names, 'total']]
        value = new_episode.load_names[0]

    return options, value


@app.callback(
    Output("env_charts_ts", "figure"),
    [Input("asset_selector", "value"),
     Input("relayoutStoreMicro", "data"),
     Input("window", "data")],
    [State("env_charts_ts", "figure"),
     State("environment_choices_buttons", "value")]
)
def load_context_data(equipments, relayout_data_store, window, figure, kind):
    if relayout_data_store is not None and relayout_data_store["relayout_data"]:
        relayout_data = relayout_data_store["relayout_data"]
        layout = figure["layout"]
        new_axis_layout = get_axis_relayout(figure, relayout_data)
        if new_axis_layout is not None:
            layout.update(new_axis_layout)
            return figure
    if kind is None:
        return figure
    if isinstance(equipments, str):
        equipments = [equipments]  # to make pd.series.isin() work

    if kind == "Load":
        figure["data"] = EpisodeTrace.get_load_trace_per_equipment(episode, equipments)
    if kind == "Production":
        figure["data"] = EpisodeTrace.get_all_prod_trace(episode, prod_types, equipments)
    if kind == "Hazards":
        figure["data"] = EpisodeTrace.get_hazard_trace(episode, equipments)
    if kind == "Maintenances":
        figure["data"] = EpisodeTrace.get_maintenance_trace(episode, equipments)

    if window is not None:
        figure["layout"].update(
            xaxis=dict(range=window, autorange=False)
        )

    return figure


@app.callback(
    [Output("overflow_ts", "figure"), Output("usage_rate_ts", "figure")],
    [Input("relayoutStoreMicro", "data"),
     Input("window", "data")],
    [State("overflow_ts", "figure"),
     State("usage_rate_ts", "figure"),
     State('agent_study', 'data'),
     State('agent_ref', 'data')]
)
def update_agent_ref_graph(relayout_data_store, window,
                           figure_overflow, figure_usage, study_agent, agent_ref):
    if relayout_data_store is not None and relayout_data_store["relayout_data"]:
        relayout_data = relayout_data_store["relayout_data"]
        layout_usage = figure_usage["layout"]
        new_axis_layout = get_axis_relayout(figure_usage, relayout_data)
        if new_axis_layout is not None:
            layout_usage.update(new_axis_layout)
            figure_overflow["layout"].update(new_axis_layout)
            return figure_overflow, figure_usage
    new_episode = make_episode(base_dir, study_agent, indx)
    figure_overflow["data"] = new_episode['total_overflow_trace']
    figure_usage["data"] = new_episode['usage_rate_trace']

    if window is not None:
        figure_overflow["layout"].update(
            xaxis=dict(range=window, autorange=False)
        )
        figure_usage["layout"].update(
            xaxis=dict(range=window, autorange=False)
        )

    return figure_overflow, figure_usage


@app.callback(
    Output("timeseries_table_micro", "data"),
    [Input("timeseries_table", "data")]
)
def sync_timeseries_table(data):
    return data

# @app.callback(
#     Output("interactive_graph", "figure"),
#     [Input("relayoutStoreMicro", "data"),
#      Input("user_timestamps", "value"),
#      Input("window", "data")],
#     [State("interactive_graph", "figure"),
#      State('agent_study', 'data')]
# )
# def update_interactive_graph(relayout_data_store,
#                              user_selected_timestamp, window, figure, study_agent):
#     new_episode = make_episode(base_dir, study_agent, indx)
#     if user_selected_timestamp is not None:
#         plot_helper = make_network(new_episode)
#         center_indx = new_episode.timestamps.index(
#             dt.datetime.strptime(user_selected_timestamp, '%Y-%m-%d %H:%M')
#         )
#         fig = get_network_graph(plot_helper, new_episode)
#         # fig = plot_helper.get_plot_observation(new_episode.observations[center_indx])
#         return fig
#     else:
#         raise PreventUpdate
