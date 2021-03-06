# models.py
# Author: Farzan Memarian

from utils import *
from adagrad_trainer import *
from treedata import *
import numpy as np
from pdb import set_trace
from sklearn.linear_model import LogisticRegression
from scipy import sparse
from scipy.misc import logsumexp
import math
import sys
import os
from random import shuffle
sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

# Greedy parsing model. This model treats shift/reduce decisions as a multiclass classification problem.
class GreedyModel(object):
	def __init__(self, feature_indexer, feature_weights, extra_features):
		self.feature_indexer = feature_indexer
		self.feature_weights = feature_weights
		self.extra_features = extra_features
		# TODO: Modify or add arguments as necessary


	# Given a ParsedSentence, returns a new ParsedSentence with predicted dependency information.
	# The new ParsedSentence should have the same tokens as the original and new dependencies constituting
	# the predicted parse.
	def parse(self, sentence):

		# label_indexer = get_label_indexer()
		parser_state = initial_parser_state(len(sentence))
		while not parser_state.is_finished():
			probability_array = np.zeros(len(parser_state.legal_actions()))
			for decision_idx, decision in enumerate(parser_state.legal_actions()):
				
				# decision = label_indexer.get_object(decision_idx)
				
				posterior_num = self.feature_weights.score(extract_features(\
					self.feature_indexer, sentence, parser_state, decision, self.extra_features,add_to_indexer=False))
				# posterior_denum = logsumexp([self.feature_weights.score(extract_features(\
				# 	self.feature_indexer, sentence, parser_state, decision, add_to_indexer=False))\
				# 	                 for decision_idx in range(len(label_indexer))])
				posterior = posterior_num #- posterior_denum
				probability_array[decision_idx] = posterior
			final_decision = parser_state.legal_actions()[np.argmax(probability_array)]
			parser_state = parser_state.take_action(final_decision)

		return ParsedSentence(sentence.tokens, parser_state.get_dep_objs(len(sentence)) )

# Returns a GreedyModel trained over the given treebank.
def train_greedy_model(parsed_sentences, extra_features="True", epochs=5):

	nb_sentences = len(parsed_sentences)
	print "Extracting features"
	feature_indexer = Indexer()
	label_indexer = get_label_indexer()
	# 4-d list indexed by sentence index, word index, tag index, feature index
	# feature_cache = [[[[] for k in xrange(0, len(get_decision_sequence(parsed_sentences[i])[0]) )] \
	# 					  for j in xrange(0, len(get_decision_sequence(parsed_sentences[i])[1]) )] \
	# 					  for i in xrange(0, len(parsed_sentences))]

	# calculating feature_cache with 3 dimentions
	feature_cache = [[[[] for k in xrange(0, len(label_indexer))] \
						  for j in xrange(0, len(get_decision_sequence(parsed_sentences[i])[1]) )] \
						  for i in xrange(0, len(parsed_sentences))]
	for sentence_idx, sentence in enumerate(parsed_sentences):
		if sentence_idx % 5000 == 0:
			print "Ex " + repr(sentence_idx) + "/" + repr(nb_sentences)
		decisions, states = get_decision_sequence(sentence)

		for state_idx, state in enumerate(states):
			for decision_idx in range(len(label_indexer)):
				decision = label_indexer.get_object(decision_idx)
				feature_cache[sentence_idx][state_idx][decision_idx] = extract_features(feature_indexer, \
							sentence, state, decision, extra_features,add_to_indexer=True)


	# creating a sparce matrix based on the gold decisions
	# data = []
	# row  = []
	# col  = []
	# row_counter = 0
	# true_labels = []
	# for sentence_idx, state_action in enumerate(feature_cache):
	# 	sentence = parsed_sentences[sentence_idx]
	# 	decisions, states = get_decision_sequence(sentence)
	# 	for state_idx, state in enumerate(state_action):
	# 		decision = decisions[state_idx]
	# 		true_labels.append(decision)
	# 		col.extend(feature_cache[sentence_idx][state_idx])
	# 		for feat_idx in feature_cache[sentence_idx][state_idx]:
	# 			row.append(row_counter)
	# 			data.append(1)
	# 		row_counter += 1
	# number_train_examples = row_counter
	# feature_mat = sparse.coo_matrix((data,(row,col)),shape=(number_train_examples, \
	# 	len(feature_indexer))).tocsr()


	# logistic = LogisticRegression(penalty='l2', dual=False, tol=0.0001, C=1.0, fit_intercept=True, \
	# 	intercept_scaling=1, class_weight=None, random_state=None, solver='liblinear', \
	# 	max_iter=100, multi_class='ovr', verbose=0, warm_start=False, n_jobs=1)
	# logistic.fit(feature_mat, true_labels)
	# score = logistic.score(feature_mat, true_labels)
	# print ("score of logistic regression:")
	# print (score)


	print "start training greedy...."
	# SGD
	print "number of epochs: ", epochs
	lamb=1e-5 
	eta=1.0
	# feature_weights = np.random.rand(len(feature_indexer))
	feature_weights = AdagradTrainer(np.zeros(len(feature_indexer)), lamb, eta)
	for epoch in range(epochs):
		print "running epoch: ", epoch
		# shuffle(parsed_sentences)
		for sentence_idx, sentence in enumerate(parsed_sentences):
			decisions, states = get_decision_sequence(sentence)
			for state_idx, state in enumerate(states):
				if state_idx < len(states) - 1:
					gradient = Counter()
					gold_dec_idx = label_indexer.get_index(decisions[state_idx])
					gradient.increment_all(feature_cache[sentence_idx][state_idx][gold_dec_idx],1)
					for decision_idx in range(len(label_indexer)): 
						posterior_num = feature_weights.score(feature_cache[sentence_idx][state_idx][decision_idx])
						posterior_denum = logsumexp([feature_weights.score(feature_cache[sentence_idx][state_idx][decision_idx2])\
						                                for decision_idx2 in range(len(label_indexer))])
						posterior = posterior_num - posterior_denum
						gradient.increment_all(feature_cache[sentence_idx][state_idx][decision_idx], -np.exp(posterior))
					feature_weights.apply_gradient_update(gradient, batch_size=1)
	print "end training "
	np.savetxt('feature_weights', feature_weights.get_final_weights())
	return GreedyModel(feature_indexer, feature_weights, extra_features)#  .get_final_weights())
	# return BeamedModel(feature_indexer, feature_weights, 1)#  .get_final_weights())

# Beam-search-based global parsing model. Shift/reduce decisions are still modeled with local features, but scores are
# accumulated over the whole sequence of decisions to give a "global" decision.
class BeamedModel(object):
	def __init__(self, feature_indexer, feature_weights, extra_features, beam_size=1):
		self.feature_indexer = feature_indexer
		self.feature_weights = feature_weights
		self.beam_size = beam_size
		self.extra_features = extra_features
		# TODO: Modify or add arguments as necessary

	# Given a ParsedSentence, returns a new ParsedSentence with predicted dependency information.
	# The new ParsedSentence should have the same tokens as the original and new dependencies constituting
	# the predicted parse.
	def parse(self, sentence):
		label_indexer = get_label_indexer()
		parser_state = initial_parser_state(len(sentence))
		beam_arr = []
		
		beam = Beam(self.beam_size)
		beam.add([parser_state ,"0"], 0) # the fist beam stores the initial state, and the score does not matter
		beam_arr.append(beam)

		for beam_counter in range(2*len(sentence)):
			beam = Beam(self.beam_size) # create a beam for the currenct state/action pair
			old_beam = beam_arr[beam_counter] # get the previous beam 
			for parser_state, decision_old in old_beam.get_elts(): # get every state of the old beam
				for decision in parser_state.legal_actions(): # iterate through the legal decisions for every beam
					candidate_state = parser_state.take_action(decision) 
					score = self.feature_weights.score(extract_features(\
							self.feature_indexer, sentence, parser_state, decision, self.extra_features,add_to_indexer=False))
					beam.add([candidate_state, decision_old + decision], score) 
			beam_arr.append(beam)
		parser_state = beam_arr[-1].head()[0]
		action_sequence = beam_arr[-1].head()[1]
		


		return ParsedSentence(sentence.tokens, parser_state.get_dep_objs(len(sentence))), action_sequence

	def parse_early_stopping(self, sentence):
		label_indexer = get_label_indexer()
		parser_state = initial_parser_state(len(sentence))
		beam_arr = []
		
		beam = Beam(self.beam_size)
		beam.add([parser_state ,"0"], 0) # the fist beam stores the initial state, and the score does not matter
		beam_arr.append(beam)

		gold_action_sequence, gold_states = get_decision_sequence(sentence) # get gold states and decisions for the sentence
		gold_dec_sequence = "0"
		for seq_dec_idx, decision in enumerate(gold_action_sequence): 
			state_idx = seq_dec_idx
			parser_state = gold_states[seq_dec_idx]
			gold_dec_idx = label_indexer.get_index(gold_action_sequence[state_idx])
			gold_dec_sequence = gold_dec_sequence + decision

		for beam_counter in range(2*len(sentence)):
			beam = Beam(self.beam_size) # create a beam for the currenct state/action pair
			old_beam = beam_arr[beam_counter] # get the previous beam 
			for parser_state, decision_old in old_beam.get_elts(): # get every state of the old beam
				for decision in parser_state.legal_actions(): # iterate through the legal decisions for every beam
					candidate_state = parser_state.take_action(decision) 
					score = self.feature_weights.score(extract_features(\
							self.feature_indexer, sentence, parser_state, decision, self.extra_features,add_to_indexer=False))
					beam.add([candidate_state, decision_old + decision], score) 
			# if not gold_dec_sequence in beam[:][]
			beam_arr.append(beam)
			parser_state = beam_arr[-1].head()[0]
			action_sequence = beam_arr[-1].head()[1]
			if not gold_dec_sequence[beam_counter+1] in [elem[1][-1] for elem in beam_arr[-1].get_elts()]: 
				break


		parser_state = beam_arr[-1].head()[0]
		action_sequence = beam_arr[-1].head()[1]
		return action_sequence



		# raise Exception("IMPLEMENT ME")


# Returns a BeamedModel trained over the given treebank.
def train_beamed_model_old(parsed_sentences, extra_features="True", epochs=5):

	nb_sentences = len(parsed_sentences)
	print "Extracting features"
	feature_indexer = Indexer()
	label_indexer = get_label_indexer()
	# 4-d list indexed by sentence index, word index, tag index, feature index
	# feature_cache = [[[[] for k in xrange(0, len(get_decision_sequence(parsed_sentences[i])[0]) )] \
	# 					  for j in xrange(0, len(get_decision_sequence(parsed_sentences[i])[1]) )] \
	# 					  for i in xrange(0, len(parsed_sentences))]

	# calculating feature_cache with 3 dimentions
	feature_cache = [[[[] for k in xrange(0, len(label_indexer))] \
						  for j in xrange(0, len(get_decision_sequence(parsed_sentences[i])[1]) )] \
						  for i in xrange(0, len(parsed_sentences))]
	for sentence_idx, sentence in enumerate(parsed_sentences):
		if sentence_idx % 5000 == 0:
			print "Ex " + repr(sentence_idx) + "/" + repr(nb_sentences)
		decisions, states = get_decision_sequence(sentence)
		for state_idx, state in enumerate(states):
			for decision_idx in range(len(label_indexer)):
				decision = label_indexer.get_object(decision_idx)
				feature_cache[sentence_idx][state_idx][decision_idx] = extract_features(feature_indexer, \
							sentence, state, decision, extra_features,add_to_indexer=True)

	print "start training beam...."
	epochs = 5
	print "number of epochs:", epochs
	lamb=1e-5 
	eta=1.0
	# set_trace()
	feature_weights = AdagradTrainer(np.zeros(len(feature_indexer)), lamb, eta)
	beam_size = 5
	print "beam size: ", beam_size
	for epoch in range(epochs):
		print "running epoch: ", epoch
		for sentence_idx, sentence in enumerate(parsed_sentences):
			gradient = Counter() # create a new gradient counter for every sentence

			gold_action_sequence, gold_states = get_decision_sequence(sentence) # get gold states and decisions for the sentence
			for seq_dec_idx, decision in enumerate(gold_action_sequence): 
				state_idx = seq_dec_idx
				parser_state = gold_states[seq_dec_idx]
				gold_dec_idx = label_indexer.get_index(gold_action_sequence[state_idx])
				feat = extract_features(feature_indexer, sentence, parser_state, decision, extra_features,add_to_indexer=False)
				# feat = feature_cache[sentence_idx][state_idx][gold_dec_idx]
				gradient.increment_all(feat,1)

			beamModel = BeamedModel(feature_indexer, feature_weights, beam_size)
			parsed_beam_sen, action_sequence = beamModel.parse(sentence) # get the prediction of the beam model
			parser_state = initial_parser_state(len(sentence))
			for seq_dec_idx, decision in enumerate(action_sequence[1:]): # iterate through the action-sequence stored in beam model
				feat = extract_features(feature_indexer, sentence, parser_state, decision, extra_features,add_to_indexer=False)
				parser_state = parser_state.take_action(decision)
				gradient.increment_all(feat,-1)
			
			# set_trace()
			# sum_grad = 0
			# for key in gradient.keys():
			# 	sum_grad += gradient.get_count(key)
			# print "sum_grad = ", sum_grad 
			feature_weights.apply_gradient_update(gradient, batch_size=1)

	return BeamedModel(feature_indexer, feature_weights, beam_size, extra_features)#  .get_final_weights())
	# raise Exception("IMPLEMENT ME")


def train_beamed_model(parsed_sentences, early_stopping=True, beam_size=5, extra_features=True, epochs=5):

	nb_sentences = len(parsed_sentences)
	print "Extracting features"
	feature_indexer = Indexer()
	label_indexer = get_label_indexer()
	# 4-d list indexed by sentence index, word index, tag index, feature index
	# feature_cache = [[[[] for k in xrange(0, len(get_decision_sequence(parsed_sentences[i])[0]) )] \
	# 					  for j in xrange(0, len(get_decision_sequence(parsed_sentences[i])[1]) )] \
	# 					  for i in xrange(0, len(parsed_sentences))]

	# calculating feature_cache with 3 dimentions
	feature_cache = [[[[] for k in xrange(0, len(label_indexer))] \
						  for j in xrange(0, len(get_decision_sequence(parsed_sentences[i])[1]) )] \
						  for i in xrange(0, len(parsed_sentences))]
	for sentence_idx, sentence in enumerate(parsed_sentences):
		if sentence_idx % 5000 == 0:
			print "Ex " + repr(sentence_idx) + "/" + repr(nb_sentences)
		decisions, states = get_decision_sequence(sentence)
		for state_idx, state in enumerate(states):
			for decision_idx in range(len(label_indexer)):
				decision = label_indexer.get_object(decision_idx)
				feature_cache[sentence_idx][state_idx][decision_idx] = extract_features(feature_indexer, \
							sentence, state, decision, extra_features,add_to_indexer=True)

	print "start training beam...."
	print "number of epochs:", 
	lamb=1e-5 
	eta=1.0
	# set_trace()
	feature_weights = AdagradTrainer(np.zeros(len(feature_indexer)), lamb, eta)
	print "beam size: ", beam_size
	for epoch in range(epochs):
		print "running epoch: ", epoch
		for sentence_idx, sentence in enumerate(parsed_sentences):
			gradient = Counter() # create a new gradient counter for every sentence

			if early_stopping == True:
				beamModel = BeamedModel(feature_indexer, feature_weights, beam_size)
				# parsed_beam_sen, action_sequence = beamModel.parse(sentence) # get the prediction of the beam model
				action_sequence = beamModel.parse_early_stopping(sentence) # get the prediction of the beam model
				parser_state = initial_parser_state(len(sentence))
				for seq_dec_idx, decision in enumerate(action_sequence[1:]): # iterate through the action-sequence stored in beam model
					feat = extract_features(feature_indexer, sentence, parser_state, decision, extra_features,add_to_indexer=False)
					parser_state = parser_state.take_action(decision)
					gradient.increment_all(feat,-1)

				gold_action_sequence, gold_states = get_decision_sequence(sentence) # get gold states and decisions for the sentence
				for seq_dec_idx, decision in enumerate(gold_action_sequence[:len(action_sequence)-1]): 
					state_idx = seq_dec_idx
					parser_state = gold_states[seq_dec_idx]
					gold_dec_idx = label_indexer.get_index(gold_action_sequence[state_idx])
					feat = extract_features(feature_indexer, sentence, parser_state, decision, extra_features,add_to_indexer=False)
					# feat = feature_cache[sentence_idx][state_idx][gold_dec_idx]
					gradient.increment_all(feat,1)


			else:
				gold_action_sequence, gold_states = get_decision_sequence(sentence) # get gold states and decisions for the sentence
				for seq_dec_idx, decision in enumerate(gold_action_sequence): 
					state_idx = seq_dec_idx
					parser_state = gold_states[seq_dec_idx]
					gold_dec_idx = label_indexer.get_index(gold_action_sequence[state_idx])
					feat = extract_features(feature_indexer, sentence, parser_state, decision, extra_features,add_to_indexer=False)
					# feat = feature_cache[sentence_idx][state_idx][gold_dec_idx]
					gradient.increment_all(feat,1)

				beamModel = BeamedModel(feature_indexer, feature_weights, beam_size)
				parsed_beam_sen, action_sequence = beamModel.parse(sentence) # get the prediction of the beam model
				parser_state = initial_parser_state(len(sentence))
				for seq_dec_idx, decision in enumerate(action_sequence[1:]): # iterate through the action-sequence stored in beam model
					feat = extract_features(feature_indexer, sentence, parser_state, decision, extra_features,add_to_indexer=False)
					parser_state = parser_state.take_action(decision)
					gradient.increment_all(feat,-1)


			
			# set_trace()
			# sum_grad = 0
			# for key in gradient.keys():
			# 	sum_grad += gradient.get_count(key)
			# print "sum_grad = ", sum_grad 
			feature_weights.apply_gradient_update(gradient, batch_size=1)

	return BeamedModel(feature_indexer, feature_weights, beam_size)#  .get_final_weights())
	# raise Exception("IMPLEMENT ME")



# Stores state of a shift-reduce parser, namely the stack, buffer, and the set of dependencies that have
# already been assigned. Supports various accessors as well as the ability to create new ParserStates
# from left_arc, right_arc, and shift.
class ParserState(object):
	# stack and buffer are lists of indices
	# The stack is a list with the top of the stack being the end
	# The buffer is a list with the first item being the front of the buffer (next word)
	# deps is a dictionary mapping *child* indices to *parent* indices
	# (this is the one-to-many map; parent-to-child doesn't work in map-like data structures
	# without having the values be lists)
	def __init__(self, stack, buffer, deps):
		self.stack = stack
		self.buffer = buffer
		self.deps = deps

	def __repr__(self):
		return repr(self.stack) + " " + repr(self.buffer) + " " + repr(self.deps)

	def __eq__(self, other):
		if isinstance(other, self.__class__):
			return self.stack == other.stack and self.buffer == other.buffer and self.deps == other.deps
		else:
			return False

	def __ne__(self, other):
		return not self.__eq__(other)

	def stack_len(self):
		return len(self.stack)

	def buffer_len(self):
		return len(self.buffer)

	def is_legal(self):
		return self.stack[0] == -1

	def legal_actions(self):

# def get_label_indexer():
# 	label_indexer = Indexer()
# 	label_indexer.get_index("L")
# 	label_indexer.get_index("R")
# 	label_indexer.get_index("S")
# 	return label_indexer

		if self.stack_len() == 1 and self.buffer_len() > 0:
			decisions = ["S"]

		elif self.stack_len() == 2 and self.buffer_len() == 0:
			decisions = ["R"]

		elif self.stack_len() == 2 and self.buffer_len() > 0:
			decisions = ["R","S"]

		elif self.buffer_len() == 0:
			decisions = ["L","R"]

		else:
			decisions = ["L","R","S"]
		return decisions			

	def is_finished(self):
		return len(self.buffer) == 0 and len(self.stack) == 1

	def buffer_head(self):
		return self.get_buffer_word_idx(0)

	# Returns the buffer word at the given index
	def get_buffer_word_idx(self, index):
		if index >= len(self.buffer):
			raise Exception("Can't take the " + repr(index) + " word from the buffer of length " + repr(len(self.buffer)) + ": " + repr(self))
		return self.buffer[index]

	# Returns True if idx has all of its children attached already, False otherwise
	def is_complete(self, idx, parsed_sentence):
		_is_complete = True
		for child in xrange(0, len(parsed_sentence)):
			if parsed_sentence.get_parent_idx(child) == idx and (child not in self.deps.keys() or self.deps[child] != idx):
				_is_complete = False
		return _is_complete

	def stack_head(self):
		if len(self.stack) < 1:
			raise Exception("Can't go one back in the stack if there are no elements: " + repr(self))
		return self.stack[-1]

	def stack_two_back(self):
		if len(self.stack) < 2:
			raise Exception("Can't go two back in the stack if there aren't two elements: " + repr(self))
		return self.stack[-2]

	# Returns a new ParserState that is the result of taking the given action.
	# action is a string, either "L", "R", or "S"
	def take_action(self, action):
		if action == "L":
			return self.left_arc()
		elif action == "R":
			return self.right_arc()
		elif action == "S":
			return self.shift()
		else:
			raise Exception("No implementation for action " + action)

	# Returns a new ParserState that is the result of applying left arc to the current state. May crash if the
	# preconditions for left arc aren't met.
	def left_arc(self):
		new_deps = dict(self.deps)
		new_deps.update({self.stack_two_back(): self.stack_head()})
		new_stack = list(self.stack[0:-2])
		new_stack.append(self.stack_head())
		return ParserState(new_stack, self.buffer, new_deps)

	# Returns a new ParserState that is the result of applying right arc to the current state. May crash if the
	# preconditions for right arc aren't met.
	def right_arc(self):
		new_deps = dict(self.deps)
		new_deps.update({self.stack_head(): self.stack_two_back()})
		new_stack = list(self.stack[0:-1])
		return ParserState(new_stack, self.buffer, new_deps)

	# Returns a new ParserState that is the result of applying shift to the current state. May crash if the
	# preconditions for right arc aren't met.
	def shift(self):
		new_stack = list(self.stack)
		new_stack.append(self.buffer_head())
		return ParserState(new_stack, self.buffer[1:], self.deps)

	# Return the Dependency objects corresponding to the dependencie
	# added so far to this ParserState
	def get_dep_objs(self, sent_len):
		dep_objs = []
		for i in xrange(0, sent_len):
			dep_objs.append(Dependency(self.deps[i], "?"))
		return dep_objs


# Returns an initial ParserState for a sentence of the given length. Note that because 
# the stack and buffer are maintained as indices, knowing the words isn't necessary.
def initial_parser_state(sent_len):
	return ParserState([-1], range(0, sent_len), {})


# Returns an indexer for the three actions so you can iterate over them easily.
def get_label_indexer():
	label_indexer = Indexer()
	label_indexer.get_index("L")
	label_indexer.get_index("R")
	label_indexer.get_index("S")
	return label_indexer


def my_standard_arc(sentence):
	gold_deps = sentence.get_deps()
	parser_state = initial_parser_state(len(sentence))

	while not parser_state.is_finished(): 
		if parser_state.stack_len() > 2:
			head_idx = parser_state.stack_head()
			two_back_idx = parser_state.stack_two_back()
			if sentence.get_parent_idx(two_back_idx) == head_idx:
				parser_state = parser_state.take_action("L")
			elif sentence.get_parent_idx(head_idx) == two_back_idx:
				head_idx_children = [index for index, token in enumerate(sentence.deps) if token.parent_idx == head_idx]
				unassigned_deps = []
				for child in head_idx_children:
					if not child in parser_state.deps.keys():
						unassigned_deps.append(child)
				if len(unassigned_deps) == 0:					
					parser_state = parser_state.take_action("R")
				elif parser_state.buffer_len() > 0:
					parser_state = parser_state.take_action("S")
			elif parser_state.buffer_len() > 0:
				parser_state = parser_state.take_action("S")

		elif parser_state.stack_len() == 2:
			head_idx = parser_state.stack_head()

			if sentence.get_parent_idx(head_idx) == -1:
				head_idx_children = [index for index, token in enumerate(sentence.deps) if token.parent_idx == head_idx]
				unassigned_deps = []
				for child in head_idx_children:
					if not child in parser_state.deps.keys():
						unassigned_deps.append(child)
				if len(unassigned_deps) == 0:					
					parser_state = parser_state.take_action("R")
				elif parser_state.buffer_len() > 0:
					parser_state = parser_state.take_action("S")
			elif parser_state.buffer_len() > 0:
				parser_state = parser_state.take_action("S")


		elif parser_state.stack_len() == 1 and parser_state.buffer_len() > 0:
			parser_state = parser_state.take_action("S")

		elif parser_state.stack_len() == 1 and parser_state.buffer_len() == 0:
			break



# Extract features for the given decision in the given parser state. Features look at the top of the
# stack and the start of the buffer. Note that this isn't in any way a complete feature set -- play around with
# more of your own!
def extract_features(feat_indexer, sentence, parser_state, decision, extra_features, add_to_indexer):
	feats = []
	sos_tok = Token("<s>", "<S>", "<S>")
	root_tok = Token("<root>", "<ROOT>", "<ROOT>")
	eos_tok = Token("</s>", "</S>", "</S>")
	if parser_state.stack_len() >= 1:
		head_idx = parser_state.stack_head()
		stack_head_tok = sentence.tokens[head_idx] if head_idx != -1 else root_tok
		if parser_state.stack_len() >= 2:
			two_back_idx = parser_state.stack_two_back()
			stack_two_back_tok = sentence.tokens[two_back_idx] if two_back_idx != -1 else root_tok
		else:
			stack_two_back_tok = sos_tok
	else:
		stack_head_tok = sos_tok
		stack_two_back_tok = sos_tok

	buffer_first_tok  = sentence.tokens[parser_state.get_buffer_word_idx(0)] if parser_state.buffer_len() >= 1 else eos_tok
	buffer_first_tok_idx = parser_state.get_buffer_word_idx(0) if parser_state.buffer_len() >= 1 else -2
	buffer_second_tok = sentence.tokens[parser_state.get_buffer_word_idx(1)] if parser_state.buffer_len() >= 2 else eos_tok
	buffer_second_tok_idx = parser_state.get_buffer_word_idx(1) if parser_state.buffer_len() >= 2 else -2
	# Shortcut for adding features
	def add_feat(feat):
		maybe_add_feature(feats, feat_indexer, add_to_indexer, feat)

	# Features that are added
	add_feat(decision + ":S0Word=" + stack_head_tok.word)
	add_feat(decision + ":S0Pos=" + stack_head_tok.pos)
	add_feat(decision + ":S0CPos=" + stack_head_tok.cpos)
	add_feat(decision + ":S1Word=" + stack_two_back_tok.word)
	add_feat(decision + ":S1Pos=" + stack_two_back_tok.pos)
	add_feat(decision + ":S1CPos=" + stack_two_back_tok.cpos)
	add_feat(decision + ":B0Word=" + buffer_first_tok.word)
	add_feat(decision + ":B0Pos=" + buffer_first_tok.pos)
	add_feat(decision + ":B0CPos=" + buffer_first_tok.cpos)
	add_feat(decision + ":B1Word=" + buffer_second_tok.word)
	add_feat(decision + ":B1Pos=" + buffer_second_tok.pos)
	add_feat(decision + ":B1CPos=" + buffer_second_tok.cpos)
	add_feat(decision + ":S1S0Pos=" + stack_two_back_tok.pos + "&" + stack_head_tok.pos)
	add_feat(decision + ":S0B0Pos=" + stack_head_tok.pos + "&" + buffer_first_tok.pos)
	add_feat(decision + ":S1B0Pos=" + stack_two_back_tok.pos + "&" + buffer_first_tok.pos)
	add_feat(decision + ":S0B1Pos=" + stack_head_tok.pos + "&" + buffer_second_tok.pos)
	add_feat(decision + ":B0B1Pos=" + buffer_first_tok.pos + "&" + buffer_second_tok.pos)
	add_feat(decision + ":S0B0WordPos=" + stack_head_tok.word + "&" + buffer_first_tok.pos)
	add_feat(decision + ":S0B0PosWord=" + stack_head_tok.pos + "&" + buffer_first_tok.pos)
	add_feat(decision + ":S1S0WordPos=" + stack_two_back_tok.word + "&" + stack_head_tok.pos)
	add_feat(decision + ":S1S0PosWord=" + stack_two_back_tok.pos + "&" + stack_head_tok.word)
	add_feat(decision + ":S1S0B0Pos=" + stack_two_back_tok.pos + "&" + stack_head_tok.pos + "&" + buffer_first_tok.pos)
	add_feat(decision + ":S0B0B1Pos=" + stack_head_tok.pos + "&" + buffer_first_tok.pos + "&" + buffer_second_tok.pos)
	# extra features
	if extract_features:
		S0N0_distance_int = head_idx - buffer_first_tok_idx
		S0N0_distance = str(S0N0_distance_int)
		add_feat(decision + ":S0wN0wd=" + stack_head_tok.word + "&" + buffer_first_tok.word + "&" + S0N0_distance )
		add_feat(decision + ":S0pN0pd=" + stack_head_tok.pos + "&" + buffer_first_tok.pos + "&" + S0N0_distance )
		add_feat(decision + ":S0wd="    + stack_head_tok.word +  "&" + str(head_idx) )
		add_feat(decision + ":S0pd="    + stack_head_tok.pos +  "&" + str(head_idx) )
		add_feat(decision + ":N0wd="    + buffer_first_tok.word +  "&" + str(buffer_first_tok_idx) )
		add_feat(decision + ":N0pd="    + buffer_first_tok.pos +  "&" + str(buffer_first_tok_idx) )
	return feats


# Computes the sequence of decisions and ParserStates for a gold-standard sentence using the arc-standard
# transition framework. We use the minimum stack-depth heuristic, namely that
# Invariant: states[0] is the initial state. Applying decisions[i] to states[i] yields states[i+1].
def get_decision_sequence(parsed_sentence):
	decisions = []
	states = []
	state = initial_parser_state(len(parsed_sentence))
	while not state.is_finished():
		if not state.is_legal():
			raise Exception(repr(decisions) + " " + repr(state))
		# Look at whether left-arc or right-arc would add correct arcs
		if len(state.stack) < 2:
			result = "S"
		else:
			# Stack and buffer must both contain at least one thing
			one_back = state.stack_head()
			two_back = state.stack_two_back()
			# -1 is the ROOT symbol, so this forbids attaching the ROOT as a child of anything
			# (passing -1 as an index around causes crazy things to happen so we check explicitly)
			if two_back != -1 and parsed_sentence.get_parent_idx(two_back) == one_back and state.is_complete(two_back, parsed_sentence):
				result = "L"
			# The first condition should never be true, but doesn't hurt to check
			elif one_back != -1 and parsed_sentence.get_parent_idx(one_back) == two_back and state.is_complete(one_back, parsed_sentence):
				result = "R"
			elif len(state.buffer) > 0:
				result = "S"
			else:
				result = "R" # something went wrong, buffer is empty, just do right arcs to finish the tree
		decisions.append(result)
		states.append(state)
		if result == "L":
			state = state.left_arc()
		elif result == "R":
			state = state.right_arc()
		else:
			state = state.shift()
	states.append(state)
	return (decisions, states)
