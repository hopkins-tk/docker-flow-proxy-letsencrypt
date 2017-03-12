import docker
import os
import time
import requests

from unittest import TestCase

class DFPLETestCase(TestCase):
	"""
	Original DFPLE implementation rely on DFP /put request to update certs.
	"""

	def setUp(self):
		"""
		Setup the needed environment:
		  * DFP + DFPLE
		  * client service requesting certificates
		"""

		self.test_name = os.environ.get('CI_BUILD_REF_SLUG', 'test')
		self.docker_client = docker.DockerClient(
			base_url='unix://var/run/docker.sock')


		self.docker_client.swarm.init()

		# docker network
		self.network_name = "test-network-dfple"
		self.network = self.docker_client.networks.create(name=self.network_name, driver='overlay')

		# docker-flow-proxy service
		# dfp_image = self.docker_client.images.pull('vfarcic/docker-flow-proxy')
		dfp_service = {
			'name': 'proxy_{}'.format(self.test_name),
			'image': 'vfarcic/docker-flow-proxy',
			'constraints': [],
			'endpoint_spec': docker.types.EndpointSpec(
				ports={80: 80, 443: 443, 8080: 8080}),
			'env': [ 
				"LISTENER_ADDRESS=swarm_listener_{}".format(self.test_name),
				"MODE=swarm", 
				"SERVICE_NAME=proxy_{}".format(self.test_name) ],
			'networks': [self.network_name]
		}

		# docker-flow-swarm-listener service
		# dfsl_image = self.docker_client.images.pull('vfarcic/docker-flow-swarm-listener')
		dfsl_service = {
			'name': 'swarm_listener_{}'.format(self.test_name),
			'image': 'vfarcic/docker-flow-swarm-listener',
			'constraints': ["node.role == manager"],
			'env': [ 
      			"DF_NOTIFY_CREATE_SERVICE_URL=http://proxy_le_{}:8080/v1/docker-flow-proxy-letsencrypt/reconfigure".format(self.test_name),
      			"DF_NOTIFY_REMOVE_SERVICE_URL=http://proxy_{}:8080/v1/docker-flow-proxy/remove".format(self.test_name)],
			'mounts': ['/var/run/docker.sock:/var/run/docker.sock:rw'],
			'networks': [self.network_name]
		}
		
		# docker-flow-proxy-letsencrypt service
		dfple_image = self.docker_client.images.build(
			path=os.path.dirname(os.path.abspath(__file__)),
			tag='robin/docker-flow-proxy-letsencrypt:{}'.format(self.test_name),
			quiet=False)
		dfple_service = {
			'name': 'proxy_le_{}'.format(self.test_name),
			'image': 'robin/docker-flow-proxy-letsencrypt:{}'.format(self.test_name),
			'constraints': ["node.role == manager"],
			'env': [
      			"DF_PROXY_SERVICE_NAME=proxy_{}".format(self.test_name),
      			"CERTBOT_OPTIONS=--staging",
      			"LOG=debug",
			],
			'labels': {
        		"com.df.notify": "true",
        		"com.df.distribute": "true",
        		"com.df.servicePath": "/.well-known/acme-challenge",
        		"com.df.port": "8080",
			},
			'networks': [self.network_name]
		}

		# start services
		# self.dfp_service = self.docker_client.services.create(**dfp_service)
		self.services = []
		
		self.dfp_service = self.docker_client.services.create(**dfp_service)
		self.services.append(self.dfp_service)
		
		self.dfsl_service = self.docker_client.services.create(**dfsl_service)
		self.services.append(self.dfsl_service)

		self.dfple_service = self.docker_client.services.create(**dfple_service)
		self.services.append(self.dfple_service)

	def tearDown(self):

		for service in self.services:
			service.remove()

		self.network.remove()

	def config_match(self, text):
		try:
			conf = requests.get('http://localhost:8080/v1/docker-flow-proxy/config').text
			print('CONF', conf)
			return text in conf
		except Exception, e:
			print('Error while getting config: {}'.format(e))
			return False

	def wait_until_found_in_config(self, text, timeout=30):

		_start = time.time()
		_current = time.time()
		while _current < _start + timeout:
			if self.config_match(text):
				return True
			time.sleep(1)
			_current = time.time()

		return False


	def test_one_domain(self):
		import requests
		import time
		import json

		# wait until proxy_le service has registered routes
		self.assertTrue(
			self.wait_until_found_in_config('proxy_le_{}'.format(self.test_name)),
			"docker-flow-proxy-letsencrypt service not registered.")

		# start the testing service
		test_service = {
			'name': 'test_service_{}'.format(self.test_name),
			'image': 'jwilder/whoami',
			'labels': {
		        "com.df.notify": "true",
		        "com.df.distribute": "true",
		        "com.df.serviceDomain": "{}.ks2.nibor.me".format(self.test_name),
		        "com.df.letsencrypt.host": "{}.ks2.nibor.me".format(self.test_name),
		        "com.df.letsencrypt.email": "test@test.com",
		        "com.df.servicePath": "/",
		        "com.df.srcPort": "443",
		        "com.df.port": "8000",
			},
			'networks': [self.network_name]
		}
		service = self.docker_client.services.create(**test_service)
		self.services.append(service)

		# wait until proxy_le service has registered routes
		self.assertTrue(
			self.wait_until_found_in_config('test_service_{}'.format(self.test_name)),
			"test service not registered.")

		# # wait until proxy_le service has registered routes
		# self.assertTrue(
		# 	self.wait_until_found_in_config('test_service_{}'.format(self.test_name)),
		# 	"test service not registered.")

		# i=0
		# while i < 5:
		# 	i += 1
		# 	container = self.docker_client.containers.list(filters={'name': 'proxy_le_{}'.format(self.test_name)})
		# 	if container:
		# 		print container
		# 		container = container[0]
		# 		print(json.dumps(container.attrs, indent=4))
		# 	else:
		# 		print('no container found')
		# 	time.sleep(2)

		# wait services to be up
		# time.sleep(10)

		# domain_acl = 'acl'
		# proxy_config = requests.get('http://localhost:8080/v1/docker-flow-proxy/config').text
		# self.assertNotIn(domain_acl, proxy_config)



		assert False