import time
import urllib.parse
from typing import Dict, Optional, Union

import requests

# MainContentExtractor
from main_content_extractor import MainContentExtractor
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


# Pydantic Models
class ActionParams(BaseModel):
	text: Optional[str] = None
	url: Optional[str] = None
	id: Optional[int] = None


class Action(BaseModel):
	valuation_previous_goal: str
	goal: str
	action: str
	params: Optional[ActionParams] = None

	@property
	def is_valid(self) -> bool:
		if self.action == 'click':
			return self.params is not None and self.params.id is not None
		return True


class ActionResult(BaseModel):
	done: bool = False
	extracted_content: str = ''
	user_input: str = ''
	error: Optional[str] = None


class BrowserActions:
	def __init__(self, driver: webdriver.Chrome):
		self.driver = driver
		self.wait = WebDriverWait(driver, 10)
		self.selector_map: Dict[int, str] = {}

	def update_selector_map(self, selector_map: Dict[int, str]):
		"""Update the current selector map"""
		self.selector_map = selector_map

	def execute_action(self, action: Action, selector_map: Dict[int, str]):
		# print(action.model_dump().keys())
		print(action.model_dump_json(indent=4))
		action_name = action.action
		self.update_selector_map(selector_map)

		# params = action.params.model_dump() if action.params else {}
		output = ActionResult()
		try:
			if action_name == 'search_google':
				if action.params and action.params.text:
					self.search_google(action.params.text)
				else:
					raise Exception('Query is required for search_google action')
			elif action_name == 'nothing':
				pass
			elif action_name == 'go_to_url':
				if action.params and action.params.url:
					self.go_to_url(action.params.url)
				else:
					raise Exception('Url is required for go_to_url action')
			elif action_name == 'go_back':
				self.go_back()
			elif action_name == 'done':
				output.done = True

			elif action_name == 'text_input':
				if action.params and action.params.id and action.params.text:
					self.input_text_by_index(action.params.id, action.params.text)
				else:
					raise Exception('Id and text are required for input action')
			elif action_name == 'click':
				if action.params and (action.params.id or action.params.id == 0):
					self.click_element_by_index(action.params.id)
				else:
					raise Exception('Id is required for click action')
			elif action_name == 'ask_user':
				if action.params and action.params.text:
					output.user_input = self.ask_user(action.params.text)
				else:
					raise Exception('Question is required for ask_user action')
			elif action_name == 'send_user_text':
				if action.params and action.params.text:
					self.send_user_text(action.params.text)
				else:
					raise Exception('Text is required for send_user_text action')
			elif action_name == 'extract_page_content':
				output.extracted_content = self.extract_page_content()
			# elif action_name == 'accept_cookies':
			#     self.driver.accept_cookies()
			else:
				raise Exception(f'Action {action_name} not found')

		except Exception as e:
			output.error = str(e)

		return output

	def done(self):
		print('\n' + '=' * 50)
		print('✅ Task completed successfully!')
		print('=' * 50)
		return True

	def click_element_by_index(self, index: int):
		"""
		Clicks an element using its index from the selector map with improved element finding strategies.
		"""
		if int(index) not in self.selector_map:
			print(f'Selector map: {self.selector_map}')
			raise Exception(f'Element index {index} not found in selector map')

		xpath = self.selector_map[int(index)]
		# print(f'Trying to click element with xpath: {xpath}')

		# Wait for any overlays/popups to disappear
		time.sleep(0.5)  # Brief wait for page to stabilize

		try:
			# Try multiple strategies to find the element
			for strategy in [
				lambda: self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath))),
				lambda: self.wait.until(EC.presence_of_element_located((By.XPATH, xpath))),
				lambda: self.driver.find_element(By.XPATH, xpath),
				# Try with simplified XPath
				lambda: self.wait.until(
					EC.element_to_be_clickable(
						(
							By.XPATH,
							f"//*[@id='{xpath.split('id=')[-1].split(']')[0]}']"
							if 'id=' in xpath
							else xpath,
						)
					)
				),
				# Try finding by any visible matching element
				lambda: next(
					elem
					for elem in self.driver.find_elements(
						By.XPATH, "//*[not(ancestor-or-self::*[@style='display: none'])]"
					)
					if elem.is_displayed() and elem.is_enabled()
				),
			]:
				try:
					element = strategy()
					if element and element.is_displayed() and element.is_enabled():
						# Scroll into view with JavaScript
						self.driver.execute_script(
							"arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
							element,
						)
						time.sleep(0.5)  # Wait for scroll to complete

						# Try both JavaScript click and regular click
						try:
							self.driver.execute_script('arguments[0].click();', element)
						except:
							element.click()
						return
				except:
					continue

			raise Exception(f'Could not find clickable element with xpath: {xpath}')

		except Exception as e:
			print(f'Failed to click element. Error: {str(e)}')
			raise Exception(f'Failed to click element with index {index}, xpath: {xpath}')

	def input_text_by_index(self, index: int, text: str):
		if int(index) not in self.selector_map:
			raise Exception(f'Element index {index} not found in selector map')

		xpath = self.selector_map[int(index)]

		try:
			# Wait for element to be both present and interactable
			element = self.wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))

			# Scroll element into view
			self.driver.execute_script(
				"arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element
			)
			time.sleep(0.5)  # Wait for scroll

			# Try to clear using JavaScript first
			self.driver.execute_script("arguments[0].value = '';", element)

			# Then send keys
			element.send_keys(text)

		except Exception as e:
			raise Exception(
				f'Failed to input text into element with index {index}, xpath: {xpath}. Error: {str(e)}'
			)

	# default actions
	def search_google(self, query: str):
		"""
		Performs a Google search with the provided query using direct URL.
		"""
		# Encode the query for URL

		encoded_query = urllib.parse.quote(query)

		search_url = f'https://www.google.com/search?q={encoded_query}'
		self.driver.get(search_url)

	def go_to_url(self, url: str):
		"""
		Navigates the browser to the specified URL.
		"""
		self.driver.get(url)

	def go_back(self):
		"""
		Navigates back in the browser history.
		"""
		self.driver.back()

	def extract_page_content(self):
		"""
		Extracts the page content.
		"""
		try:
			response = requests.get(self.driver.current_url)
			response.encoding = 'utf-8'
			content = response.text
			extracted_markdown = MainContentExtractor.extract(content, output_format='markdown')
			return extracted_markdown
		except Exception as e:
			print(f'Error getting main content: {e}')
			return ''

	def ask_user(self, question: str):
		"""
		Talks to the user.
		"""
		print(question)
		print('--------------------------------\nInput: \n ')
		user_input = input()
		return user_input

	def send_user_text(self, text: str):
		"""
		Sends text to the user.
		"""
		print(text)
		print('--------------------------------')

	def get_default_actions(self) -> dict[str, str]:
		return {
			'search_google': 'text: string',
			'go_to_url': 'url: string',
			'done': '',
			'go_back': '',
			'click': 'id: int',
			'text_input': 'id: int, text: string',
			'nothing': '',
			'extract_page_content': '',
			'ask_user': 'text: string',
			'send_user_text': 'text: string',
		}
		# 'accept_cookies': '',
