from collections import OrderedDict
from dataclasses import dataclass, field
from itertools import chain, islice
from typing import List, Tuple
import streamlit as st
from streamlit_tags import st_tags, st_tags_sidebar
import pandas as pd
import numpy as np
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe
from st_aggrid import AgGrid, GridOptionsBuilder

# Define the color palette
PRIMARY_COLOR = "#1976d2"
SECONDARY_COLOR = "#f48fb1"
BG_COLOR = "#f9f9f9"
TEXT_COLOR = "#333333"
GRAY_COLOR = "#aaaaaa"
RED_COLOR = "#f44336"
GREEN_COLOR = "#4caf50"

# Set up the Google Sheets API credentials
creds = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["gcp_service_account"],
    ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"],
)
gc = gspread.authorize(creds)

SHEET_NAME = st.secrets["SHEET_NAME"]
HEADER_ROW = st.secrets["HEADER_ROW"]
HEADER_NON_BRANCH_COL_COUNT = st.secrets["HEADER_NON_BRANCH_COL_COUNT"]


@dataclass(order=True)
class GroceryPrice:
    name: str = field(compare=False)
    tags: List[str] = field(compare=False)
    size: int = field(compare=False)
    denominator: int = field(compare=False)
    unit: str = field(compare=False)
    branch: str = field(compare=False)
    price: float = field(compare=False)
    unit_price: float = field(init=False)

    def __post_init__(self):
        self.unit_price = self.price * self.denominator / self.size


def get_branches_from_sheet(sheet_name: str) -> List:
    sheet = gc.open(sheet_name).sheet1
    return sheet.row_values(1)[HEADER_NON_BRANCH_COL_COUNT:]


# Define the Google Sheets API functions
def read_prices_from_sheet(sheet_name):
    sheet = gc.open(sheet_name).sheet1
    data = sheet.get_all_values()
    header = data[0]
    prices = {}
    for row in data[1:]:
        grocery_item = row[0]
        options = row[1].split("|")
        if grocery_item not in prices:
            prices[grocery_item] = []
        for i in range(len(row) - 5):
            if (price := row[5 + i]) != "":
                prices[grocery_item].append(
                    GroceryPrice(
                        name=grocery_item,
                        tags=options,
                        size=float(row[2]),
                        denominator=int(row[3]),
                        unit=row[4],
                        branch=header[5 + i],
                        price=float(price),
                    )
                )
    return prices


def write_prices_to_sheet(sheet_name, prices):
    gc = gspread.authorize(creds)
    sheet = gc.open(sheet_name).sheet1
    sheet.clear()
    header = [
        "Grocery Item",
        "Options",
        "Size",
        "Denominator",
        "Unit",
        "Unit Price",
    ] + list(
        prices[list(prices.keys())[0]][
            list(prices[list(prices.keys())[0]].keys())[0]
        ].keys()
    )
    data = [header]
    for grocery_item in prices:
        for option in prices[grocery_item]:
            row = (
                [grocery_item, option]
                + [
                    prices[grocery_item][option][col]
                    for col in ["Size", "Denominator", "Unit", "Unit Price"]
                ]
                + [prices[grocery_item][option][chain] for chain in header[6:]]
            )
            data.append(row)
    sheet.update(data)


def get_cheapest_item_from_sorted(sorted_list: List[GroceryPrice]):
    return [i for i in sorted_list if i.unit_price == sorted_list[0].unit_price]


def chunk(arr_range, arr_size):
    arr_range = iter(arr_range)
    return iter(lambda: tuple(islice(arr_range, arr_size)), ())


def display_table(df: pd.DataFrame) -> AgGrid:

    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(editable=True)
    grid_table = AgGrid(
        df,
        # height=400,
        gridOptions=gb.build(),
        fit_columns_on_grid_load=True,
        allow_unsafe_jscode=True,
    )
    return grid_table


# Define the Streamlit app
def app():
    # Set the page title and header
    st.set_page_config(page_title="Grocery Price Tracker", page_icon="🍎", layout="wide")
    st.title("Grocery Price Tracker")

    # Create a search box for the grocery item and tag
    prices = read_prices_from_sheet(SHEET_NAME)
    grocery_items = list(prices.keys())
    tags = list(
        set(
            chain.from_iterable(
                item.tags
                for item in chain.from_iterable(items for _, items in prices.items())
            )
        )
    )
    selected_tags = st.multiselect("Search:", [""] + tags)
    selected_item = st.selectbox("Select Grocery Item", [""] + grocery_items, index=0)

    st.markdown("""---""")

    if (not selected_item) and (not selected_tags):
        st.markdown(
            """
            ## Welcome to the Grocery Price Tracker!
            
            This app allows you to search for grocery items and see their prices across different chains.
        
            ### How to use this app

            1. Type the name of a grocery item or a tag in the search box on the left.
            2. Click on an item from the list to see its prices across different chains.
            3. Use the dropdown menu to select a chain and add or update the price.
            4. Click the "Add/Update Price" button to save the price to the Google Sheet.
            
            ### Tips

            - You can use tags to search for related items. For example, typing "noodles" will show all kinds of noodles, including udon, ramen, and more.
            - If you don't see the grocery item you're looking for, click the "Add Item" button to add it to the list.
            - You can click on other items in the list to see their prices too.
            
            ### Happy shopping! 🛒👩‍🌾👨‍🌾
        """
        )
    else:

        # Display the options for the selected grocery item
        # options = list(prices[selected_item].keys())

        # Display the prices for the selected grocery item and option
        # st.header(f"{selected_item|selected_tags}")

        filtered_items = []
        for k, items in prices.items():
            if (selected_item != "") and (k != selected_item):
                continue
            if not selected_tags:
                filtered_items.extend(items)
                continue
            for item in items:
                if len(np.intersect1d(item.tags, selected_tags)) == len(selected_tags):
                    filtered_items.append(item)

        cheapest_items = get_cheapest_item_from_sorted(filtered_items)
        other_items = filtered_items[len(cheapest_items) :]

        st.subheader("Cheapest Options")

        container = st.container()

        for row in chunk(cheapest_items, 3):
            cols = container.columns(3)
            for item, col in zip(row, cols):
                col.metric(
                    label=item.name + " - " + item.branch,
                    value=f"£ {item.unit_price:,.2f} / {'' if item.denominator == 1 else item.denominator}{item.unit}",
                    delta=", ".join(item.tags)
                    + f" {item.size} {item.unit} £{item.price:,.2f}",
                    delta_color="off",
                )

        st.markdown("""---""")

        st.subheader("Other Options")

        container = st.container()

        for row in chunk(other_items, 3):
            cols = container.columns(3)
            for item, col in zip(row, cols):
                col.metric(
                    label=item.name + " - " + item.branch,
                    value=f"£ {item.unit_price:,.2f} / {'' if item.denominator == 1 else item.denominator}{item.unit}",
                    delta=", ".join(item.tags)
                    + f" {item.size} {item.unit} £{item.price:,.2f}",
                    delta_color="off",
                )

        st.markdown("""---""")

    # Read the contents of the worksheet into a pandas DataFrame
    worksheet = gc.open(SHEET_NAME).sheet1
    df = pd.DataFrame(worksheet.get_all_records())

    container = st.container()
    with container.form(key="new_item_form") as new_branch_form:
        name = st.text_input("Item Name")
        options = st.text_input("Options (Comma-delimited)")
        size = st.number_input("Size", min_value=0.1)
        denominator = st.number_input("Denominator", min_value=1, format="%g")
        unit = st.text_input("Unit")
        submit_button = st.form_submit_button("Add")
        if submit_button:
            if not name:
                st.error("Item name cannot be empty!")
            elif not unit:
                st.error("Unit cannot be empty!")
            else:
                new_row = pd.Series(
                    data=[name, options.strip(), size, denominator, unit]
                    + ([""] * (len(df.columns) - 5)),
                    index=df.columns,
                )
                df = df.append(new_row, ignore_index=True)
            # Update the worksheet with the new data
            set_with_dataframe(worksheet, df)
            st.success("Sheet updated successfully!")
            df = pd.DataFrame(worksheet.get_all_records())

    container = st.container()
    with container.form(key="new_branch_form") as new_branch_form:
        name = st.text_input("Branch Name")
        submit_button = st.form_submit_button("Add")
        if submit_button:
            if not name:
                st.error("Branch name cannot be empty!")
            elif (name := name.strip()) in df.columns:
                st.error(f"{name} already exists!")
            else:
                df[name.strip()] = pd.Series(dtype=float)
            # Update the worksheet with the new data
            set_with_dataframe(worksheet, df)
            st.success("Sheet updated successfully!")
            df = pd.DataFrame(worksheet.get_all_records())

    # Display the DataFrame as an interactive table using st.dataframe()
    table = display_table(df)

    save_table_button = st.button("Save Price Change")
    if save_table_button:
        df = pd.DataFrame(table["data"])
        # Update the worksheet with the new data
        set_with_dataframe(worksheet, df)
        st.success("Sheet updated successfully!")


# Run the app
if __name__ == "__main__":
    app()
