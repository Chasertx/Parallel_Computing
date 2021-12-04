import sys
import numba 
import numpy as np
from numba import cuda
from numba.cuda.random import create_xoroshiro128p_states, xoroshiro128p_uniform_float64

@cuda.jit
def blackjack_kernel(wins_standing_array,
                     wins_hitting_array,
                     remaining_deck_array,
                     player_hand_array,
                     dealer_hand_array,
                     starting_player_sum,
                     starting_dealer_sum,
                     simulations_to_run,
                     rng_states):

    def get_random_card_index(rng, thread_pos, card_count):
        """ Big wrapper for "getting a random int" up to 1 less than card_count """
        random_float = xoroshiro128p_uniform_float64(rng, thread_pos) # [0, 1) evenly distributed
        random_int = int(card_count * random_float) # truncates
        return random_int

    def smart_add(current_sum, value_to_add):
        #return current_sum + value_to_add
        sum = current_sum + value_to_add
        if value_to_add == 11 and sum > 21:
            sum -= 10

        return sum

    thread_position = cuda.threadIdx.x

    wins_standing_count = 0
    wins_hitting_count = 0
    cards_left_in_deck = remaining_deck_array.size

    # array representing card indeces (in remaining_deck_array) that are in-play.
    # Since this can't be dynamically allocated, just assigning 52
    cards_in_play = numba.cuda.local.array(52, numba.types.boolean)

    
    #add dealer's uknown card
        # flush deck (reset taken cards)
    #check initial busts
    is_dealer_busted = False
    if starting_dealer_sum < 22:
        is_dealer_busted = False
    else:
        is_dealer_busted = True
    for idx in range(52):
        cards_in_play[idx] = False
    is_dealer_took_turn = False
        ##because I dont want to add a smart_unadd
    temp_sum = starting_dealer_sum

        ##loop to check dealer drew an acceptable card
    index = 0
    while not is_dealer_took_turn and not is_dealer_busted:
        random_card_index = get_random_card_index(rng_states, thread_position, cards_left_in_deck)
        if not cards_in_play[random_card_index + index]:
            cards_in_play[random_card_index + index] = True
            temp_sum = starting_dealer_sum
            temp_sum = smart_add(temp_sum, remaining_deck_array[random_card_index])
            
            if (temp_sum < 22):
                is_dealer_took_turn = True
                starting_dealer_sum = temp_sum
            else:
                index = index - 1
                

    # begin simulations
    for _ in range(simulations_to_run):
        # flush deck (reset taken cards)
        for idx in range(52):
            cards_in_play[idx] = False

        player_sum = starting_player_sum
        dealer_sum = starting_dealer_sum
        dealer_sum_standing = starting_dealer_sum

        #check initial busts
        if starting_dealer_sum < 22:
            is_dealer_busted = False
        else:
            is_dealer_busted = True
        #if the player busts -< automatic loss
        if player_sum < 22:
            is_player_busted = False
        else:
            is_player_busted = False


        #------------------------STANDING:
        ##just the dealer plays
        is_dealer_done = False
        while not is_dealer_busted and not is_dealer_done:
            if dealer_sum_standing < 17:
                found_an_unused_card_index = False
                while not found_an_unused_card_index:
                    random_card_index = get_random_card_index(rng_states, thread_position, cards_left_in_deck)
                    if not cards_in_play[random_card_index]:
                       cards_in_play[random_card_index] = True
                       dealer_sum_standing = smart_add(dealer_sum_standing, remaining_deck_array[random_card_index])
                       found_an_unused_card_index = True
                       if dealer_sum_standing > 21:
                            is_dealer_busted = True  
            else:
                is_dealer_done = True

        ##the 3 "win" conditions
        if player_sum > dealer_sum_standing and not is_player_busted:
            wins_standing_count += 1
        elif player_sum == dealer_sum_standing and not is_player_busted and not is_dealer_busted:
            wins_standing_count += .5
        elif not is_player_busted and is_dealer_busted:
            wins_standing_count += 1

        # --- Now we do different logic for both possibilities
        #---------------------------HITTING:
       

        # flush deck (reset taken cards)
        for idx in range(52):
            cards_in_play[idx] = False

        # reset dealer bust
        if starting_dealer_sum < 22:
            is_dealer_busted = False
        else:
            is_dealer_busted = True

        #for turn loop, parties having their final sum without busting
        is_both_done = False
        is_player_done = False
        is_dealer_done = False
        ##turn loop, exit conditions are someone busting or both parties having their final sum
       # while (not is_player_busted and not is_dealer_busted) and (not is_player_done and not is_dealer_done):
        while not is_player_busted and not is_player_busted and not is_both_done:
            #player turn
            if player_sum < 19: ##we should make this an input in the begining
                found_an_unused_card_index = False
                while not found_an_unused_card_index:
                    random_card_index = get_random_card_index(rng_states, thread_position, cards_left_in_deck)
                    if not cards_in_play[random_card_index]:
                        cards_in_play[random_card_index] = True
                        player_sum = smart_add(player_sum, remaining_deck_array[random_card_index])
                        found_an_unused_card_index = True
                        if player_sum > 21:
                            is_player_busted = True
            else:
                is_player_done = True
            #dealer turn
            if dealer_sum < 17 and not is_player_busted: ##dealer doesnt have to go if player busts
                found_an_unused_card_index = False
                while not found_an_unused_card_index:
                    random_card_index = get_random_card_index(rng_states, thread_position, cards_left_in_deck)
                    if not cards_in_play[random_card_index]:
                        cards_in_play[random_card_index] = True
                        dealer_sum = smart_add(dealer_sum, remaining_deck_array[random_card_index])
                        found_an_unused_card_index = True
                        if dealer_sum > 21:
                            is_dealer_busted = True  
            else:
                is_dealer_done = True
            if(is_dealer_done and is_player_done):
                is_both_done = True
            

        ##the 3 "win" conditions
        if player_sum > dealer_sum and not is_player_busted:
            wins_hitting_count += 1
        elif player_sum == dealer_sum and not is_player_busted and not is_dealer_busted:
            wins_hitting_count += .5
        elif not is_player_busted and is_dealer_busted:
            wins_hitting_count += 1

    wins_standing_array[thread_position] = wins_standing_count
    wins_hitting_array[thread_position] =  wins_hitting_count

def get_card_values_from_hand_str(hand):
    card_str_list = hand.split(",")
    value_list = []
    for card in card_str_list:
        value_list.append(card_str_to_value(card))
    return card_str_list, value_list

def card_str_to_value (card):
    """ Takes a human-readable card string and gets the underlying card value.
        Ace is 11, Face cards are 10.
    """
    if "a" in card:
        return 11
    elif "2" in card:
        return 2
    elif "3" in card:
        return 3
    elif "4" in card:
        return 4
    elif "5" in card:
        return 5
    elif "6" in card:
        return 6
    elif "7" in card:
        return 7
    elif "8" in card:
        return 8
    elif "9" in card:
        return 9
    elif "10" in card:
        return 10
    elif "j" in card:
        return 10
    elif "q" in card:
        return 10
    elif "k" in card:
        return 10

def get_total_from_value_list(value_list):
    total = 0
    numAces = 0
    for value in value_list:
        total += value
        if value == 11:
            numAces += 1
    while total > 21 and numAces > 0:
        total -= 10
        numAces -= 1
    return total

## Called by Front end for
def formatInputForBlackJack (player_hand_string, dealer_hand_string): 
    player_hand_cards_list, player_hand_values_list = get_card_values_from_hand_str(player_hand_string)
    dealer_hand_cards_list, dealer_hand_values_list = get_card_values_from_hand_str(dealer_hand_string)
    playerTotal = get_total_from_value_list(player_hand_values_list)
    dealerTotal = get_total_from_value_list(dealer_hand_values_list)
    return player_hand_cards_list, player_hand_values_list, dealer_hand_cards_list, dealer_hand_values_list, playerTotal, dealerTotal

def get_full_deck():
    """ returns an np array of all blackjack values in a deck, with aces as 11s """
    deck_value_list = list()

    # 2-11, includes one set of "10s" (the actual 10 cards) and one set of "11s" (aces)
    for card_value in range(2, 12):
        for _ in range(4):
            deck_value_list.append(card_value)
    
    # the other face cards, of which there are 12 (4 of each)
    for _ in range(12):
        deck_value_list.append(10)

    deck = np.array(deck_value_list)
    return deck

## Returns Deck with 0s where no card size 52
def initializeDeck(player_hand_values, dealer_hand_values): 
    deck = get_full_deck()
    for value in player_hand_values:
        deck = np.delete(deck, np.where(deck==value)[0][0])
    for value in dealer_hand_values:
        deck = np.delete(deck, np.where(deck==value)[0][0])
    return deck

## Returns Hand with 0s where no card size 12 (not the best implementation but I was spending too much time on this)
def normalizeHand(hand):
    hand = np.array(hand)
    zerosToAdd = 12 - hand.size
    for i in range(0,zerosToAdd):
        hand = np.insert(hand,hand.size, 0)
    return hand

def format_input_for_kernel(playerHand, dealerHand):
    player_hand_cards, player_hand_values, dealer_hand_cards, dealer_hand_values, playerTotal, dealerTotal = formatInputForBlackJack (playerHand, dealerHand)

    ## Deck values without player values or dealer known values
    deck_without_hand_values = initializeDeck(player_hand_values, dealer_hand_values)

    ##player and dealer have a fixed array size of 12, cards are non-zero (unsure how handling dealer's uknown card so for now he is treated like a player)
    playerHandNormalized = normalizeHand(player_hand_values)
    dealerHandNormalized = normalizeHand(dealer_hand_values)

    ## printing these in console so you can see (hit submit on input)
    #print(deck_without_hand_values, file=sys.stderr)
    #print(playerHandNormalized, file=sys.stderr)
    #print(dealerHandNormalized, file=sys.stderr)

    # hitOnFirst = not sure if call on kernel launch
    return playerTotal, dealerTotal, deck_without_hand_values, playerHandNormalized, dealerHandNormalized

def core_handler(num_threads_to_run, games_per_thread, player_hand_str, dealer_hand_str):
    """ Takes input directly from "routes", returns win ratios back. Handles kernel execution. """

    # get data ready for kernel
    player_total, dealer_total, remaining_deck_array, player_hand_array, dealer_hand_array = format_input_for_kernel(player_hand_str, dealer_hand_str)

    if player_total == 21 or dealer_total > 21: # player has blackjack or dealer busts
        standing_winrate = 1
        hitting_winrate = 1
    elif dealer_total == 21 or player_total > 21: # player bust or dealer has blackjack
        standing_winrate = 0
        hitting_winrate = 0
    else:
        # intial state data needed for the RNG
        rng_states = create_xoroshiro128p_states(num_threads_to_run, seed=777)

        # all zeroes, allocate arrays
        wins_standing = np.zeros(num_threads_to_run)
        wins_hitting = np.zeros(num_threads_to_run) 

        # execute kernel instances, both arrays will be updated
        blackjack_kernel[1, num_threads_to_run](wins_standing,
                                                wins_hitting,
                                                remaining_deck_array,
                                                player_hand_array,
                                                dealer_hand_array,
                                                player_total,
                                                dealer_total,
                                                games_per_thread,
                                                rng_states)

        standing_win_average = np.average(wins_standing)
        hitting_win_average = np.average(wins_hitting)
        print(wins_standing, file=sys.stderr)
        print(wins_hitting, file=sys.stderr)

        standing_winrate = standing_win_average / games_per_thread
        hitting_winrate = hitting_win_average / games_per_thread

    return standing_winrate, hitting_winrate
