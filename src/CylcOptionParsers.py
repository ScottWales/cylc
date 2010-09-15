#!/usr/bin/env python

#         __________________________
#         |____C_O_P_Y_R_I_G_H_T___|
#         |                        |
#         |  (c) NIWA, 2008-2010   |
#         | Contact: Hilary Oliver |
#         |  h.oliver@niwa.co.nz   |
#         |    +64-4-386 0461      |
#         |________________________|


# Custom derived option parsers, with standard options, for cylc commands.

# TO DO: CLEAN UP OR REDESIGN THESE CLASSES.

import os
import socket
from optparse import OptionParser

#class NoPromptOptionParser( OptionParser ):
class NoPromptOptionParser_u( OptionParser ):

    def __init__( self, usage, extra_args=None ):

        usage += """

If you are not the owner of the target suite, you must provide the
owner's username so that the Pyro nameserver group can be inferred.

Arguments:
   SUITE                Registered name of the target suite.""" 

        self.n_args = 1  # suite name
        if extra_args:
            for arg in extra_args:
                usage += '\n   ' + arg
                self.n_args += 1

        OptionParser.__init__( self, usage )

        self.add_option( "-u", "--user",
                help="Owner of the target suite (defaults to $USER).",
                metavar="USER", default=os.environ["USER"],
                action="store", dest="username" )

        self.add_option( "--host",
                help="Pyro Nameserver host (defaults to local host).",
                metavar="HOST", action="store", default=socket.getfqdn(),
                dest="pns_host" )

        self.add_option( "-p", "--practice",
                help="Target a suite running in practice mode.", 
                action="store_true", default=False, dest="practice" )

    def parse_args( self ):

        (options, args) = OptionParser.parse_args( self )

        if len( args ) == 0:
            self.error( "Please supply a target suite name" )
        elif len( args ) > self.n_args:
            self.error( "Too many arguments" )

        # suite name
        self.suite_name = args[0]

        # user name 
        self.username = options.username  # see default above!

        # nameserver host
        self.pns_host = options.pns_host   # see default above!

        self.practice = options.practice  # practice mode or not

        return ( options, args )


    def get_suite_name( self ):
        return self.suite_name

    def get_pns_host( self ):
        return self.pns_host

    def get_groupname( self ):
        # TO DO: USER PYREX MODULE HERE
        groupname = ':cylc.' + self.username + '.' + self.suite_name
        if self.practice:
            groupname += '-practice'
        return groupname


class NoPromptOptionParser( OptionParser ):
    # same, but own username

    def __init__( self, usage, extra_args=None ):

        usage += """

You must be the owner of the target suite in order to use this command.

arguments:
   SUITE                Registered name of the target suite.""" 

        self.n_args = 1  # suite name
        if extra_args:
            for arg in extra_args:
                usage += '\n   ' + arg
                self.n_args += 1


        OptionParser.__init__( self, usage )

        self.add_option( "--host",
                help="Pyro Nameserver host (defaults to local hostname).",
                metavar="HOSTNAME", action="store", default=socket.getfqdn(),
                dest="pns_host" )

        self.add_option( "-p", "--practice",
                help="Target a suite running in practice mode.", 
                action="store_true", default=False, dest="practice" )

        self.username = os.environ['USER']

    def parse_args( self ):

        (options, args) = OptionParser.parse_args( self )

        if len( args ) == 0:
            self.error( "Please supply a target suite name" )
        elif len( args ) > self.n_args:
            self.error( "Too many arguments" )

        # suite name
        self.suite_name = args[0]

        # nameserver host
        self.pns_host = options.pns_host   # see default above!

        self.practice = options.practice  # practice mode or not

        return ( options, args )


    def get_suite_name( self ):
        return self.suite_name

    def get_pns_host( self ):
        return self.pns_host

    def get_groupname( self ):
        # TO DO: USER PYREX MODULE HERE
        groupname = ':cylc.' + self.username + '.' + self.suite_name
        if self.practice:
            groupname += '-practice'
        return groupname



class PromptOptionParser( NoPromptOptionParser ):

    def __init__( self, usage, extra_args=None ):

        NoPromptOptionParser.__init__( self, usage, extra_args )

        self.add_option( "-f", "--force",
                help="Do not ask for confirmation before acting.",
                action="store_true", default=False, dest="force" )

    def parse_args( self ):

        (options, args) = NoPromptOptionParser.parse_args( self )

        if options.force:
            self.force = True
        else:
            self.force = False

        return (options, args)

    def prompt( self, reason ):
        msg =  reason + " '" + self.suite_name + "'"

        if self.force:
            return True

        response = raw_input( msg + ': ARE YOU SURE (y/n)? ' )
        if response == 'y':
            return True
        else:
            return False
